"""
Test examples for AI Moderation functionality.

This file demonstrates how to test the AI moderation features.
"""

import json
from unittest.mock import Mock, patch

from forum.ai_moderation import AIModerationService, check_content_for_spam, moderate_forum_content


def test_ai_moderation_spam_detection():
    """Test that spam content is correctly identified."""
    
    # Mock response for spam content
    spam_response = [{
        "content": json.dumps({
            "reasoning": "This post is likely spam as it invites users to join a WhatsApp group without providing any context or value. Such posts often aim to gather personal information or promote unrelated content, which is a common characteristic of spam.",
            "classification": "spam"
        })
    }]
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = spam_response
        mock_post.return_value.raise_for_status.return_value = None
        
        service = AIModerationService()
        result = service.is_content_spam("Join our WhatsApp group for free money!", "course-v1:test+test+test")
        
        assert result is True


def test_ai_moderation_legitimate_content():
    """Test that legitimate content is not flagged as spam."""
    
    # Mock response for legitimate content
    legit_response = [{
        "content": json.dumps({
            "reasoning": "This post appears to be a genuine introduction from a user named John. It contains personal information such as a name and location, and expresses enthusiasm about joining a course, which are typical characteristics of legitimate posts.",
            "classification": "not_spam"
        })
    }]
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = legit_response
        mock_post.return_value.raise_for_status.return_value = None
        
        service = AIModerationService()
        result = service.is_content_spam("Hi, my name is John, I am from Nevada, glad to be part of this course", "course-v1:test+test+test")
        
        assert result is False


def test_ai_moderation_api_failure():
    """Test that API failures default to not spam."""
    
    with patch('requests.post') as mock_post:
        mock_post.side_effect = Exception("API Error")
        
        service = AIModerationService()
        result = service.is_content_spam("Any content", "course-v1:test+test+test")
        
        assert result is False  # Default to not spam on API failure


def test_convenience_functions():
    """Test the convenience functions."""
    
    legit_response = [{
        "content": json.dumps({
            "reasoning": "This is a test post",
            "classification": "not_spam"
        })
    }]
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = legit_response
        mock_post.return_value.raise_for_status.return_value = None
        
        # Test check_content_for_spam function
        is_spam = check_content_for_spam("Test content", "course-v1:test+test+test")
        assert is_spam is False
        
        # Test moderate_forum_content function
        result = moderate_forum_content("Test content", "course-v1:test+test+test")
        assert result['is_spam'] is False
        assert 'reasoning' in result
        assert 'classification' in result


if __name__ == "__main__":
    # Run basic tests
    test_ai_moderation_spam_detection()
    test_ai_moderation_legitimate_content()
    test_ai_moderation_api_failure()
    test_convenience_functions()
    print("All tests passed!")