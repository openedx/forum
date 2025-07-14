"""
Handlers for the forum app.
"""

import logging
from typing import Any
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from forum.search import get_document_search_backend
from forum.utils import get_str_value_from_collection
from forum.models import Comment, CommentThread

log = logging.getLogger(__name__)


def handle_comment_thread_deletion(sender: Any, **kwargs: dict[str, str]) -> None:
    """
    Handle the deletion of a comment thread from the Elasticsearch index.

    Args:
        sender (Any): The model class that sends the signal.
        **kwargs (dict[str, Any]): Additional arguments, including 'comment_thread_id'.
    """
    thread_id = get_str_value_from_collection(kwargs, "comment_thread_id")
    search_backend = get_document_search_backend()
    search_backend.delete_document(sender.index_name, thread_id)


def handle_comment_deletion(sender: Any, **kwargs: dict[str, Any]) -> None:
    """
    Handle the deletion of a comment from the Elasticsearch index.

    Args:
        sender (Any): The model class that sends the signal.
        **kwargs (dict[str, Any]): Additional arguments, including 'comment_id'.
    """
    comment_id = get_str_value_from_collection(kwargs, "comment_id")
    search_backend = get_document_search_backend()
    search_backend.delete_document(sender.index_name, comment_id)


def handle_comment_thread_insertion(sender: Any, **kwargs: dict[str, Any]) -> None:  # pylint: disable=W0613
    """
    Handle the insertion of a comment thread into the Elasticsearch index.

    Args:
        sender (Any): The model class that sends the signal.
        **kwargs (dict[str, Any]): Additional arguments, including 'comment_thread_id'.
    """
    thread_id = get_str_value_from_collection(kwargs, "comment_thread_id")
    thread = sender().get(_id=thread_id)
    doc = sender().doc_to_hash(thread)
    get_document_search_backend().index_document(sender.index_name, thread_id, doc)
    log.info(f"Thread {thread_id} added to Elasticsearch index")


def handle_comment_insertion(sender: Any, **kwargs: dict[str, Any]) -> None:  # pylint: disable=W0613
    """
    Handle the insertion of a comment into the Elasticsearch index.

    Args:
        sender (Any): The model class that sends the signal.
        **kwargs (dict[str, Any]): Additional arguments, including 'comment_id'.
    """
    comment_id = get_str_value_from_collection(kwargs, "comment_id")
    comment = sender().get(_id=comment_id)
    doc = sender().doc_to_hash(comment)
    get_document_search_backend().index_document(sender.index_name, comment_id, doc)
    log.info(f"Comment {comment_id} added to Elasticsearch index")


def handle_comment_thread_updated(sender: Any, **kwargs: dict[str, Any]) -> None:
    """
    Handle the update of a comment thread in the Elasticsearch index.

    Args:
        sender (Any): The model class that sends the signal.
        **kwargs (dict[str, Any]): Additional arguments, including 'comment_thread_id'.
    """
    thread_id = get_str_value_from_collection(kwargs, "comment_thread_id")
    thread = sender().get(_id=thread_id)
    doc = sender().doc_to_hash(thread)
    get_document_search_backend().update_document(sender.index_name, thread_id, doc)
    log.info(f"Thread {thread_id} added to Elasticsearch index")


def handle_comment_updated(sender: Any, **kwargs: dict[str, Any]) -> None:
    """
    Handle the update of a comment in the Elasticsearch index.

    Args:
        sender (Any): The model class that sends the signal.
        **kwargs (dict[str, Any]): Additional arguments, including 'comment_id'.
    """
    comment_id = get_str_value_from_collection(kwargs, "comment_id")
    comment = sender().get(_id=comment_id)
    doc = sender().doc_to_hash(comment)
    get_document_search_backend().update_document(sender.index_name, comment_id, doc)
    log.info(f"Comment {comment_id} added to Elasticsearch index")


@receiver(post_delete, sender=CommentThread)
@receiver(post_delete, sender=Comment)
def handle_deletion(sender: Any, instance: Any, **kwargs: dict[str, Any]) -> None:
    """
    Handle the deletion of a comment thread or comment from the MySQL database.

    Args:
        sender (Any): The model class that sends the signal.
        instance (Any): The instance of the deleted comment thread or comment.
    """
    document_id = instance.id
    search_backend = get_document_search_backend()
    search_backend.delete_document(sender.index_name, document_id)
    log.info(f"{sender.__name__} {document_id} deleted from the search backend")


@receiver(post_save, sender=CommentThread)
@receiver(post_save, sender=Comment)
def handle_comment_thread_and_comment(
    sender: Any, instance: Any, created: bool, **kwargs: dict[str, Any]
) -> None:
    """
    Handle the insertion or update of a comment thread or comment in the MySQL database.

    Args:
        sender (Any): The model class that sends the signal.
        instance (Any): The instance of the comment thread or comment.
        created (bool): Indicates if the instance was created.
    """
    document_id = instance.id
    search_backend = get_document_search_backend()
    doc = instance.doc_to_hash()

    if created:
        search_backend.index_document(sender.index_name, document_id, doc)
        log.info(f"{sender.__name__} {document_id} added to the search backend")
    else:
        search_backend.update_document(sender.index_name, document_id, doc)
        log.info(f"{sender.__name__} {document_id} updated in the search backend")
