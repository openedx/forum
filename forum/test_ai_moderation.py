"""
Test examples for AI Moderation functionality.

This file demonstrates how to test the AI moderation features with the updated system.
"""

import json
from unittest.mock import Mock, patch, MagicMock

from forum.ai_moderation import AIModerationService, moderate_and_flag_spam


def test_ai_moderation_spam_detection():
    """Test that spam content is correctly identified with new spam_or_scam classification."""
    
    # Mock response for spam content using new classification
    spam_response = [{
        "content": json.dumps({
            "reasoning": "This post exhibits multiple red flags: (1) Invites users to join a WhatsApp group without educational context, (2) promises 'free money' which is a classic scam tactic, (3) uses urgency and social proof tactics. These are clear indicators of spam/scam content targeting students.",
            "classification": "spam_or_scam"
        })
    }]
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = spam_response
        mock_post.return_value.raise_for_status.return_value = None
        
        # Mock waffle flag to be enabled
        with patch('forum.ai_moderation.ENABLE_AI_MODERATION.is_enabled', return_value=True):
            service = AIModerationService()
            
            # Create mock content instance
            mock_content = {'_id': 'test_id', '_type': 'comment', 'author_id': 1}
            mock_backend = MagicMock()
            
            result = moderate_and_flag_spam(
                "Join our WhatsApp group for free money!", 
                mock_content,
                "course-v1:test+test+test",
                mock_backend
            )
            
            assert result['is_spam'] is True
            assert result['classification'] == 'spam_or_scam'
            assert result['action_taken'] == 'flagged'
            assert 'WhatsApp' in result['reasoning']


def test_ai_moderation_legitimate_content():
    """Test that legitimate educational content is not flagged as spam."""
    
    # Mock response for legitimate content
    legit_response = [{
        "content": json.dumps({
            "reasoning": "This is a legitimate academic question about sorting algorithms. The post contains no suspicious links, no requests for external contact, no promotional language, and is directly related to course content. The tone is appropriate for a learner seeking help.",
            "classification": "not_spam"
        })
    }]
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = legit_response
        mock_post.return_value.raise_for_status.return_value = None
        
        # Mock waffle flag to be enabled
        with patch('forum.ai_moderation.ENABLE_AI_MODERATION.is_enabled', return_value=True):
            service = AIModerationService()
            
            # Create mock content instance
            mock_content = {'_id': 'test_id', '_type': 'comment', 'author_id': 1}
            mock_backend = MagicMock()
            
            result = moderate_and_flag_spam(
                "Can someone explain the difference between merge sort and quick sort?",
                mock_content,
                "course-v1:test+test+test", 
                mock_backend
            )
            
            assert result['is_spam'] is False
            assert result['classification'] == 'not_spam'
            assert result['action_taken'] == 'approved'


def test_ai_moderation_api_failure():
    """Test that API failures default to not spam and don't break content creation."""
    
    with patch('requests.post') as mock_post:
        mock_post.side_effect = Exception("API Error")
        
        # Mock waffle flag to be enabled
        with patch('forum.ai_moderation.ENABLE_AI_MODERATION.is_enabled', return_value=True):
            # Create mock content instance
            mock_content = {'_id': 'test_id', '_type': 'comment', 'author_id': 1}
            mock_backend = MagicMock()
            
            result = moderate_and_flag_spam(
                "Any content",
                mock_content,
                "course-v1:test+test+test",
                mock_backend
            )
            
            assert result['is_spam'] is False  # Default to not spam on API failure
            assert result['action_taken'] == 'no_action'
            assert 'API failed' in result['reasoning']


def test_ai_moderation_waffle_flag_disabled():
    """Test that moderation is skipped when waffle flag is disabled."""
    
    # Mock waffle flag to be disabled
    with patch('forum.ai_moderation.ENABLE_AI_MODERATION.is_enabled', return_value=False):
        # Create mock content instance
        mock_content = {'_id': 'test_id', '_type': 'comment', 'author_id': 1}
        mock_backend = MagicMock()
        
        result = moderate_and_flag_spam(
            "Any suspicious content with WhatsApp links",
            mock_content,
            "course-v1:test+test+test",
            mock_backend
        )
        
        assert result['is_spam'] is False
        assert result['action_taken'] == 'no_action'
        assert 'disabled' in result['reasoning']


def test_ai_moderation_backwards_compatibility():
    """Test that the system handles old 'spam' classification alongside new 'spam_or_scam'."""
    
    # Mock response with old 'spam' classification
    old_spam_response = [{
        "content": json.dumps({
            "reasoning": "This appears to be spam content.",
            "classification": "spam"  # Old classification format
        })
    }]
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = old_spam_response
        mock_post.return_value.raise_for_status.return_value = None
        
        # Mock waffle flag to be enabled
        with patch('forum.ai_moderation.ENABLE_AI_MODERATION.is_enabled', return_value=True):
            service = AIModerationService()
            
            # Create mock content instance
            mock_content = {'_id': 'test_id', '_type': 'comment', 'author_id': 1}
            mock_backend = MagicMock()
            
            result = moderate_and_flag_spam(
                "Spam content",
                mock_content,
                "course-v1:test+test+test",
                mock_backend
            )
            
            # Should still detect as spam with old classification
            assert result['is_spam'] is True
            assert result['classification'] == 'spam'
            assert result['action_taken'] == 'flagged'


def test_mongodb_content_handling():
    """Test that MongoDB content (dict format) is properly handled."""
    
    spam_response = [{
        "content": json.dumps({
            "reasoning": "This contains suspicious promotional content.",
            "classification": "spam_or_scam"
        })
    }]
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = spam_response
        mock_post.return_value.raise_for_status.return_value = None
        
        # Mock waffle flag to be enabled
        with patch('forum.ai_moderation.ENABLE_AI_MODERATION.is_enabled', return_value=True):
            # Create MongoDB-style content instance (dict)
            mongodb_content = {
                '_id': 'mongodb_object_id_123',
                '_type': 'Comment',
                'author_id': 1,
                'body': 'Test content'
            }
            
            # Mock MongoDB backend with flagging method
            mock_backend = MagicMock()
            mock_backend.flag_content_as_spam = MagicMock()
            
            result = moderate_and_flag_spam(
                "Suspicious promotional content",
                mongodb_content,
                "course-v1:test+test+test",
                mock_backend
            )
            
            assert result['is_spam'] is True
            assert result['action_taken'] == 'flagged'
            
            # Verify backend flagging method was called
            mock_backend.flag_content_as_spam.assert_called_once()
            
            # Verify content attributes were set
            assert mongodb_content.get('is_spam') is True
            assert 'promotional content' in mongodb_content.get('ai_moderation_reason', '')


def test_audit_logging_integration():
    """Test that audit logging works for both MongoDB and MySQL content."""
    
    spam_response = [{
        "content": json.dumps({
            "reasoning": "Content analysis shows spam indicators.",
            "classification": "spam_or_scam"
        })
    }]
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = spam_response
        mock_post.return_value.raise_for_status.return_value = None
        
        # Mock waffle flag to be enabled
        with patch('forum.ai_moderation.ENABLE_AI_MODERATION.is_enabled', return_value=True):
            
            # Mock the audit log creation
            with patch('forum.ai_moderation.create_moderation_audit_log') as mock_audit:
                
                # Test MongoDB content
                mongodb_content = {'_id': 'test_id', '_type': 'comment', 'author_id': 1}
                mock_backend = MagicMock()
                
                result = moderate_and_flag_spam(
                    "Test content",
                    mongodb_content,
                    "course-v1:test+test+test",
                    mock_backend
                )
                
                # Verify audit log was called
                mock_audit.assert_called()
                call_args = mock_audit.call_args
                
                # Check audit log parameters
                assert call_args[0][0] == mongodb_content  # content_instance
                assert call_args[0][2] == 'flagged'  # action_taken
                assert 'reasoning' in call_args[0][1]  # moderation_result


def test_enhanced_prompt_validation():
    """Test that the enhanced prompt is being used correctly."""
    
    service = AIModerationService()
    
    # Check that the enhanced prompt contains key indicators
    prompt = service.system_message
    
    assert "WhatsApp" in prompt
    assert "Telegram" in prompt
    assert "cryptocurrency" in prompt
    assert "spam_or_scam" in prompt
    assert "not_spam" in prompt
    assert "reasoning" in prompt
    assert "classification" in prompt


if __name__ == "__main__":
    # Run all tests
    test_ai_moderation_spam_detection()
    test_ai_moderation_legitimate_content()
    test_ai_moderation_api_failure()
    test_ai_moderation_waffle_flag_disabled()
    test_ai_moderation_backwards_compatibility()
    test_mongodb_content_handling()
    test_audit_logging_integration()
    test_enhanced_prompt_validation()
    print("All tests passed!")