"""
AI Moderation utilities for forum content.
"""

import json
import logging
from typing import Dict, Optional, Any

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from opaque_keys.edx.keys import CourseKey

from forum.backends.mysql.models import ModerationAuditLog, AbuseFlagger
from forum.toggles import ENABLE_AI_MODERATION

User = get_user_model()
log = logging.getLogger(__name__)

def _set_content_attribute(content_instance: Any, attribute: str, value: Any) -> None:
    """
    Helper function to set attribute on content instance (handles both dict and model objects).
    
    Args:
        content_instance: Content object (dict for MongoDB, model for MySQL)
        attribute: Attribute name to set
        value: Value to set
    """
    if isinstance(content_instance, dict):
        content_instance[attribute] = value
    else:
        setattr(content_instance, attribute, value)


def _get_content_id(content_instance: Any) -> str:
    """
    Helper function to get content ID from content instance.
    
    Args:
        content_instance: Content object (dict for MongoDB, model for MySQL)
        
    Returns:
        String representation of content ID
    """
    if isinstance(content_instance, dict):
        return str(content_instance.get('_id', ''))
    else:
        return str(content_instance.pk)


def _get_content_type_name(content_instance: Any) -> str:
    """
    Helper function to get content type name from content instance.
    
    Args:
        content_instance: Content object (dict for MongoDB, model for MySQL)
        
    Returns:
        Content type name (e.g., 'commentthread', 'comment')
    """
    if isinstance(content_instance, dict):
        return content_instance.get('_type', 'unknown').lower()
    else:
        return content_instance.__class__.__name__.lower()


def _get_mongodb_content_type_name(content_instance: Any) -> str:
    """
    Helper function to get content type name for MongoDB backend operations.
    
    Args:
        content_instance: Content object (dict for MongoDB, model for MySQL)
        
    Returns:
        Content type name in proper case for MongoDB backend (e.g., 'CommentThread', 'Comment')
    """
    if isinstance(content_instance, dict):
        content_type = content_instance.get('_type', 'unknown')
        # Convert to proper case for MongoDB backend
        if content_type.lower() == 'commentthread':
            return 'CommentThread'
        elif content_type.lower() == 'comment':
            return 'Comment'
        else:
            return content_type
    else:
        return content_instance.__class__.__name__


def _get_author_from_content(content_instance: Any) -> Any:
    """
    Helper function to get author from content instance.
    
    Args:
        content_instance: Content object (dict for MongoDB, model for MySQL)
        
    Returns:
        Author object or user ID
    """
    if isinstance(content_instance, dict):
        # For MongoDB, we need to get the User object from author_id
        author_id = content_instance.get('author_id')
        if author_id:
            try:
                User = get_user_model()
                return User.objects.get(pk=author_id)
            except Exception:
                # If we can't get the User object, return the ID as fallback
                return author_id
        return None
    else:
        return getattr(content_instance, 'author', None)


def create_moderation_audit_log(
    content_instance: Any,
    moderation_result: Dict[str, Any],
    action_taken: str,
    original_author: Any
) -> None:
    """
    Create an audit log entry for AI moderation decisions.
    
    Args:
        content_instance: The content object (Thread or Comment, dict or model)
        moderation_result: Full result from AI moderation
        action_taken: Action taken ('flagged', 'approved', 'deleted', 'no_action')
        original_author: User who created the content
    """
    try:
        # Get author if not provided
        if original_author is None:
            original_author = _get_author_from_content(content_instance)
        
        # For MongoDB backend (dict), we need to handle content references differently
        if isinstance(content_instance, dict):
            # For MongoDB, we create audit logs without ContentType references
            # since the content isn't stored in Django models
            content_id = _get_content_id(content_instance)
            content_type_name = _get_content_type_name(content_instance)
            
            # Create a simplified audit log entry
            # We'll use a special "external_content" ContentType or create a minimal audit log
            try:
                # Try to create audit log without content_type reference
                from forum.backends.mysql.models import ModerationAuditLog
                
                # For MongoDB content, we'll store the content info in the classifier_output
                enhanced_moderation_result = moderation_result.copy()
                enhanced_moderation_result.update({
                    'content_id': content_id,
                    'content_type': content_type_name,
                    'backend_type': 'mongodb'
                })
                
                # Create audit log without content_type/content_object_id for MongoDB
                audit_log = ModerationAuditLog(
                    # Leave content_type and content_object_id as None for MongoDB
                    content_type=None,
                    content_object_id=None,
                    timestamp=timezone.now(),
                    classifier_output=enhanced_moderation_result,
                    reasoning=moderation_result.get('reasoning', 'No reasoning provided'),
                    classification=moderation_result.get('classification', 'not_spam'),
                    action_taken=action_taken,
                    confidence_score=moderation_result.get('confidence_score'),
                    original_author=original_author,
                )
                
                # Save without foreign key constraints for MongoDB content
                audit_log.save()
                
                log.info(
                    f"Created moderation audit log for MongoDB {content_type_name} {content_id}: "
                    f"classification={moderation_result.get('classification')}, action={action_taken}"
                )
                
            except Exception as db_error:
                # If database audit logging fails, fall back to application logging
                log.error(f"Failed to create database audit log for MongoDB content: {db_error}")
                log.info(
                    f"AI moderation audit - {content_type_name} {content_id}: "
                    f"classification={moderation_result.get('classification')}, "
                    f"action={action_taken}, reasoning={moderation_result.get('reasoning', '')[:100]}..."
                )
            
            return
        
        # For MySQL backend (Django models)
        content_type = ContentType.objects.get_for_model(content_instance)
        
        ModerationAuditLog.objects.create(
            content_type=content_type,
            content_object_id=content_instance.pk,
            timestamp=timezone.now(),
            classifier_output=moderation_result,
            reasoning=moderation_result.get('reasoning', 'No reasoning provided'),
            classification=moderation_result.get('classification', 'not_spam'),
            action_taken=action_taken,
            confidence_score=moderation_result.get('confidence_score'),
            original_author=original_author,
        )
        
        log.info(
            f"Created moderation audit log for {content_type.model} {content_instance.pk}: "
            f"classification={moderation_result.get('classification')}, action={action_taken}"
        )
        
    except Exception as e:
        log.error(f"Failed to create moderation audit log: {e}")


class AIModerationService:
    """Service for AI-based content moderation."""
    
    # Default API configuration
    DEFAULT_API_URL = "https://example.com"
    DEFAULT_CLIENT_ID = "example_client_id"
    DEFAULT_SYSTEM_MESSAGE = (
        "Filter posts from a discussion forum platform to identify and flag content that is likely to be spam or a scam.\n\n"
        "**Instructions**:\n"
        "- Carefully analyze each post's text for language, links, or patterns typical of spam or scams.\n"
        "- Use clear reasoning to identify suspicious indicators such as:\n"
        "  * Promotional language or unsolicited commercial content\n"
        "  * Misleading claims or \"too good to be true\" offers\n"
        "  * Excessive external links (especially non-educational domains)\n"
        "  * Requests for personal information (phone numbers, email, social media)\n"
        "  * Suspicious offers (money, investment, guaranteed results)\n"
        "  * Impersonation of authority figures (course staff, professors)\n"
        "  * Directing users to external communication platforms (WhatsApp, Telegram)\n"
        "  * Cryptocurrency, forex, or investment scheme language\n"
        "  * Urgent pressure tactics (\"act now\", \"limited time\")\n\n"
        "- After thoroughly explaining your reasoning and highlighting specific suspicious features, classify the post as either \"spam_or_scam\" or \"not_spam\".\n"
        "- **Do not make a classification before detailing your reasoning.** Always present your analysis of the post's content before your final determination.\n"
        "- If uncertainty exists, explain which factors made detection difficult before concluding.\n"
        "- Consider legitimate use cases: Course-related external links (.edu domains), genuine help requests, study group formation.\n\n"
        "**Output Format** (strict JSON):\n"
        "{\n"
        "  \"reasoning\": \"[Detailed explanation of why this post may or may not be spam/scam, referencing specific features of the post. Minimum 2 sentences.]\",\n"
        "  \"classification\": \"[spam_or_scam | not_spam]\"\n"
        "}\n\n"
        "**Examples**:\n\n"
        "Example 1 (Spam):\n"
        "Post: \"Hi everyone! I'm Professor Johnson. Contact me on WhatsApp +1-555-0123 for guaranteed A+ grades. Limited slots!\"\n"
        "Output:\n"
        "{\n"
        "  \"reasoning\": \"This post exhibits multiple red flags: (1) Impersonation of a professor with no verification, (2) request to contact via WhatsApp with phone number, (3) unrealistic promise of 'guaranteed A+ grades', (4) urgency tactic 'limited slots'. These are classic patterns of academic scams targeting students.\",\n"
        "  \"classification\": \"spam_or_scam\"\n"
        "}\n\n"
        "Example 2 (Not Spam):\n"
        "Post: \"Can someone explain the difference between merge sort and quick sort? I'm struggling with the time complexity analysis.\"\n"
        "Output:\n"
        "{\n"
        "  \"reasoning\": \"This is a legitimate academic question about sorting algorithms. The post contains no suspicious links, no requests for external contact, no promotional language, and is directly related to course content. The tone is appropriate for a learner seeking help.\",\n"
        "  \"classification\": \"not_spam\"\n"
        "}"
    )
    
    def __init__(self):
        """Initialize the AI moderation service."""
        self.api_url = getattr(settings, 'AI_MODERATION_API_URL', self.DEFAULT_API_URL)
        self.client_id = getattr(settings, 'AI_MODERATION_CLIENT_ID', self.DEFAULT_CLIENT_ID)
        self.system_message = getattr(settings, 'AI_MODERATION_SYSTEM_MESSAGE', self.DEFAULT_SYSTEM_MESSAGE)
        self.timeout = getattr(settings, 'AI_MODERATION_TIMEOUT', 30)  # seconds
        
    def _make_api_request(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Make API request to AI moderation service.
        
        Args:
            content: The text content to moderate
            
        Returns:
            Dictionary with 'reasoning' and 'classification' keys, or None if failed
        """
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0 (compatible; edX-Forum-AI-Moderation/1.0)',
        }
        
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "client_id": self.client_id,
            "system_message": self.system_message
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            response_data = response.json()

            assistant_content = response_data[0].get('content', '')
            # Parse the JSON content from the assistant response
            try:
                moderation_result = json.loads(assistant_content)
                # full API response for audit purposes
                moderation_result['full_api_response'] = response_data
                return moderation_result
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse AI moderation response JSON: {e}")
                return None
        except Exception as e:
            log.error(f"AI moderation API request failed: {e}")
            return None
    
    def moderate_and_flag_content(
        self, 
        content: str, 
        content_instance: Any, 
        course_id: Optional[str] = None,
        backend: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Moderate content and flag as spam if detected.
        
        Args:
            content: The text content to check
            content_instance: The content model instance (Thread or Comment)
            course_id: Optional course ID for waffle flag checking
            backend: Backend instance for database operations
            
        Returns:
            Dictionary with moderation results and actions taken
        """
        result = {
            'is_spam': False,
            'reasoning': 'AI moderation disabled or unavailable',
            'classification': 'not_spam',
            'action_taken': 'no_action',
            'flagged': False
        }
        
        # Check if AI moderation is enabled
        if not self._is_ai_moderation_enabled(course_id):
            return result
            
        # Make API request
        moderation_result = self._make_api_request(content)
        
        if moderation_result is None:
            result['reasoning'] = 'AI moderation API failed'
            # Create audit log for API failure
            create_moderation_audit_log(
                content_instance,
                {'reasoning': 'API failure', 'classification': 'not_spam'},
                'no_action',
                _get_author_from_content(content_instance)
            )
            return result
            
        classification = moderation_result.get('classification', 'not_spam')
        reasoning = moderation_result.get('reasoning', 'No reasoning provided')
        is_spam = classification in ['spam', 'spam_or_scam']
        
        result.update({
            'is_spam': is_spam,
            'reasoning': reasoning,
            'classification': classification,
            'moderation_result': moderation_result
        })
        
        if is_spam:
            try:
                # Mark content as spam
                _set_content_attribute(content_instance, 'is_spam', True)
                _set_content_attribute(content_instance, 'ai_moderation_reason', reasoning)
                
                if backend:
                    # Use backend method to flag content
                    self._flag_content_as_abuse(content_instance, backend)
                else:
                    # Fallback: use Django model directly
                    self._flag_content_directly(content_instance)
                
                result['action_taken'] = 'flagged'
                result['flagged'] = True
                
                content_type_name = _get_content_type_name(content_instance)
                content_id = _get_content_id(content_instance)
                
                log.info(
                    f"AI moderation flagged {content_type_name} {content_id} as spam"
                )
                
            except Exception as e:
                log.error(f"Failed to flag content as spam: {e}")
                result['action_taken'] = 'no_action'
        else:
            result['action_taken'] = 'approved'
        
        # Create audit log
        create_moderation_audit_log(
            content_instance,
            moderation_result,
            result['action_taken'],
            _get_author_from_content(content_instance)
        )
        
        return result
    
    def _flag_content_as_abuse(self, content_instance: Any, backend: Any) -> None:
        """Flag content as abuse using backend methods."""
        try:
            # Try to use backend's flagging mechanism if available
            content_id = _get_content_id(content_instance)
            
            if hasattr(backend, 'flag_content_as_spam'):
                # Use MongoDB backend's flagging method if available
                content_type = _get_mongodb_content_type_name(content_instance)
                backend.flag_content_as_spam(content_type, content_id, "Spam detected by AI classifier")

            elif hasattr(backend, 'flag_as_abuse'):                
                # Create a system user for AI moderation if it doesn't exist
                system_user, _ = User.objects.get_or_create(
                    username='ai_moderation_system',
                    defaults={
                        'email': 'ai-moderation@system.edx',
                        'first_name': 'AI',
                        'last_name': 'Moderation System',
                        'is_active': False,  # System user, not a real user
                    }
                )
                backend.flag_as_abuse(str(system_user.id), content_id)
            else:
                # Fallback to direct model flagging
                self._flag_content_directly(content_instance)
                
        except Exception as e:
            log.error(f"Failed to flag content via backend: {e}")
            # Fallback to direct flagging
            self._flag_content_directly(content_instance)
    
    def _flag_content_directly(self, content_instance: Any) -> None:
        """Flag content directly using Django models."""
        try:
            # This method only works with Django model objects, not dicts
            if isinstance(content_instance, dict):
                log.warning("Cannot flag content directly - content_instance is a dict (MongoDB backend)")
                return

            # Create a system user for AI moderation if it doesn't exist
            system_user, _ = User.objects.get_or_create(
                username='ai_moderation_system',
                defaults={
                    'email': 'ai-moderation@system.edx',
                    'first_name': 'AI',
                    'last_name': 'Moderation System',
                    'is_active': False,  # System user, not a real user
                }
            )
            
            content_type = ContentType.objects.get_for_model(content_instance)
            
            # Create abuse flag entry
            AbuseFlagger.objects.get_or_create(
                user=system_user,
                content_type=content_type,
                content_object_id=content_instance.pk,
                defaults={'flagged_at': timezone.now()}
            )
            
            log.info(f"Flagged {content_type.model} {content_instance.pk} as abuse")
            
        except Exception as e:
            log.error(f"Failed to flag content directly: {e}")

    def _is_ai_moderation_enabled(self, course_id: Optional[str] = None) -> bool:
        """Check if AI moderation is enabled via waffle flag."""
        if course_id:
            course_key = CourseKey.from_string(course_id)
            return ENABLE_AI_MODERATION.is_enabled(course_key)
        else:
            # If no course_id, check if it's enabled globally
            return ENABLE_AI_MODERATION.is_enabled()


# Global instance
ai_moderation_service = AIModerationService()

def moderate_and_flag_spam(
    content: str,
    content_instance: Any,
    course_id: Optional[str] = None,
    backend: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Moderate content and flag as spam if detected.
    
    Args:
        content: The text content to moderate
        content_instance: The content model instance
        course_id: Optional course ID for waffle flag checking
        backend: Backend instance for database operations
        
    Returns:
        Dictionary with moderation results and actions taken
    
    TODO:- 
     - Add content check for images
    """
    return ai_moderation_service.moderate_and_flag_content(
        content, content_instance, course_id, backend
    )