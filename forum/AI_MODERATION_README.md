# AI Moderation for Forum Content

This module provides AI-powered spam and scam detection for forum threads and comments with comprehensive audit logging and content flagging capabilities.

## Overview

The AI moderation system integrates with a third-party API to analyze forum content and automatically detect spam/scam posts. Instead of deleting content, it flags posts as abuse while maintaining audit trails and allowing human oversight.

## Features

- **Smart Content Flagging**: Content identified as spam is flagged rather than deleted
- **Comprehensive Audit Logging**: Complete audit trail of all moderation decisions
- **Database Integration**: Supports both MySQL and MongoDB backends  
- **Human Override Support**: Moderators can override AI decisions
- **Waffle Flag Control**: Can be enabled/disabled per course using Django waffle flags
- **Robust Error Handling**: API failures don't affect normal forum operations
- **Monitoring & Analytics**: Track moderation effectiveness and patterns

## Architecture Changes

### Database Fields Added

#### Content Models (CommentThread & Comment)
- `is_spam` (Boolean): Whether content was flagged as spam by AI
- `ai_moderation_reason` (Text): AI reasoning if flagged as spam

#### New Model: ModerationAuditLog
- Comprehensive audit logging for all AI moderation decisions
- Tracks classifier output, reasoning, actions taken
- Supports human moderator overrides
- Links to original content and authors

### MongoDB Schema Updates

For existing MongoDB deployments, the AI moderation fields are automatically supported through the updated backend models. The MongoDB backend includes:

- **Content Documents**: New fields `is_spam` and `ai_moderation_reason` are added to thread and comment documents
- **Flagging Integration**: Content flagging uses the existing `abuse_flaggers` system with AI system integration
- **Audit Logging**: Uses the shared MySQL-based audit logging system for consistency across backends

No separate schema migration is required - the backend handles the new fields gracefully.

## Files Added/Modified

### New Files
- `ai_moderation.py` - Enhanced AI moderation service with flagging and audit logging
- `migrations/0004_add_ai_moderation_fields.py` - Database migration
- `test_ai_moderation.py` - Test examples and usage demonstrations
- `settings_ai_moderation_example.py` - Django settings configuration examples

### Modified Files
- `backends/mysql/models.py` - Added ModerationAuditLog model and spam fields
- `backends/mongodb/api.py` - Added AI moderation flagging methods for MongoDB support
- `backends/mongodb/threads.py` - Added spam fields to thread model
- `backends/mongodb/comments.py` - Added spam fields to comment model
- `toggles.py` - Added `ENABLE_AI_MODERATION` waffle flag
- `api/threads.py` - Updated to use flagging instead of deletion
- `api/comments.py` - Updated to use flagging instead of deletion

## Configuration

### Waffle Flag
Enable AI moderation per course using the waffle flag:
```
discussions.enable_ai_moderation
```

### Django Settings
Add these settings to your Django configuration:

```python
# AI Moderation API Configuration
AI_MODERATION_API_URL = "https://xpert-api-services.prod.ai.2u.com/v1/message"
AI_MODERATION_CLIENT_ID = "edx-harvard-forum-spam"
AI_MODERATION_TIMEOUT = 30  # seconds
```

## Usage

### Automatic Operation
Once enabled via waffle flag, AI moderation runs automatically for:
- New thread creation (`create_thread`)
- New parent comment creation (`create_parent_comment`) 
- New child comment creation (`create_child_comment`)

### Content Flow with AI Moderation
```
User creates content → Content saved successfully → AI moderation check → 
If spam: Flag as abuse + audit log → User sees success response
If not spam: Approve + audit log → User sees success response
```

### Programmatic Usage

#### Flag Content and Create Audit Log
```python
from forum.ai_moderation import moderate_and_flag_spam

# For new content during creation
moderation_result = moderate_and_flag_spam(
    content="Content to check",
    content_instance=thread_or_comment_object,
    course_id="course-v1:test+test+test",
    backend=backend_instance
)

if moderation_result['is_spam']:
    print(f"Content flagged: {moderation_result['reasoning']}")
```

#### Basic Spam Check (No Action)
```python
from forum.ai_moderation import check_content_for_spam

is_spam = check_content_for_spam("Suspicious content", "course-v1:test+test+test")
```

### MongoDB Integration

For MongoDB deployments, AI moderation functionality provides content flagging:

```python
# AI moderation flagging methods are available through the MongoDB backend
from forum.backends.mongodb.api import MongoBackend

# Flag content as spam  
MongoBackend.flag_content_as_spam(
    content_type="CommentThread",
    content_id="thread_id", 
    reason="Spam detected by AI classifier"
)

# Remove spam flag
MongoBackend.unflag_content_as_spam(
    content_type="CommentThread",
    content_id="thread_id"
)

# Note: Audit logging uses the shared MySQL-based system
# for consistency across all backend types
```

## API Integration

### Request Format
The service sends requests to the AI moderation API with:
```json
{
  "messages": [
    {"role": "user", "content": "Content to moderate"}
  ],
  "client_id": "edx-harvard-forum-spam",
  "system_message": "Filter posts from a discussion forum platform..."
}
```

### Response Format
Expected API response:
```json
[{
  "content": "{\"reasoning\": \"Detailed explanation...\", \"classification\": \"spam\"}"
}]
```

## Audit Log Schema

Each moderation action creates an audit log with:

- **Content Reference**: Links to the moderated content
- **Timestamp**: When the decision was made
- **Classifier Output**: Full AI response including confidence scores
- **Reasoning**: Human-readable explanation
- **Classification**: 'spam' or 'not_spam'
- **Action Taken**: 'flagged', 'approved', 'deleted', or 'no_action'
- **Human Override Info**: Moderator details and override reason if applicable
- **Original Author**: Who created the content

## Error Handling & Resilience

- **API Failures**: Default to not spam to avoid false positives
- **Network Issues**: Log errors but don't affect forum operation  
- **Parsing Errors**: Gracefully handle malformed API responses
- **Waffle Flag Disabled**: Skip moderation entirely
- **Database Errors**: Ensure audit logging failures don't break content creation

## Monitoring & Analytics

### Key Metrics to Monitor
- Spam detection rate over time
- False positive/negative rates (via human overrides)
- API response times and failure rates
- Content flagging trends by course

### Built-in Statistics
```python
from forum.backends.mysql.models import ModerationAuditLog

# Get recent spam detection rate
recent_logs = ModerationAuditLog.objects.filter(
    timestamp__gte=timezone.now() - timedelta(days=7)
)
spam_rate = recent_logs.filter(classification='spam').count() / recent_logs.count()
```

## Security Considerations

- API credentials should be stored securely in environment variables
- Timeouts prevent hanging requests from affecting forum performance
- Error handling ensures forum functionality isn't disrupted by moderation failures
- Audit logs provide transparency and accountability
- Human override capability prevents AI mistakes from being permanent

## Testing

Run the included tests:
```bash
python /workspaces/edx-repos/src/forum/forum/test_ai_moderation.py
```

Or integrate with your Django test suite using the test examples provided.

## Migration Guide

### From Previous Version (Silent Deletion)

1. **Run Database Migration**:
   ```bash
   python manage.py migrate forum 0004
   ```

2. **Update MongoDB Integration** (if using MongoDB):
   ```python
   # The MongoDB backend automatically supports the new fields
   # No separate schema update required - handled by the backend
   ```

3. **Update Code References**:
   - Replace `check_content_for_spam()` calls with `moderate_and_flag_spam()`
   - Update any custom moderation logic to handle flagging instead of deletion

4. **Configure Monitoring**:
   - Set up regular audit log reviews
   - Monitor spam detection rates
   - Train moderators on override procedures

## Troubleshooting

### Common Issues

**AI Moderation Not Working**
- Check waffle flag is enabled for the course
- Verify API credentials and network connectivity
- Check Django logs for API errors

**High False Positive Rate**
- Review audit logs to identify patterns
- Consider adjusting system message prompts
- Use human overrides to correct mistakes

**Performance Issues**
- Monitor API response times
- Consider increasing timeout settings
- Review audit log cleanup schedule

### Debug Mode
Enable verbose logging:
```python
import logging
logging.getLogger('forum.ai_moderation').setLevel(logging.DEBUG)
```