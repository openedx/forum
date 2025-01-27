"""Client backend for forum v2."""

import math
import random
from datetime import timedelta
from typing import Any, Optional, Union

from django.contrib.auth.models import User  # pylint: disable=E5142
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db.models import (
    Count,
    Case,
    Exists,
    F,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    When,
    Sum,
)
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from forum.backends.backend import AbstractBackend
from forum.backends.mysql.models import (
    AbuseFlagger,
    Comment,
    CommentThread,
    CourseStat,
    EditHistory,
    ForumUser,
    HistoricalAbuseFlagger,
    LastReadTime,
    ReadState,
    Subscription,
    UserVote,
)
from forum.constants import RETIRED_BODY, RETIRED_TITLE
from forum.utils import get_group_ids_from_params


class MySQLBackend(AbstractBackend):
    """MySQL backend api."""

    @classmethod
    def update_stats_for_course(
        cls, user_id: str, course_id: str, **kwargs: Any
    ) -> None:
        """Update stats for a course."""
        user = User.objects.get(pk=user_id)
        course_stat, created = CourseStat.objects.get_or_create(
            user=user, course_id=course_id
        )
        if created:
            course_stat.active_flags = 0
            course_stat.inactive_flags = 0
            course_stat.threads = 0
            course_stat.responses = 0
            course_stat.replies = 0

        for key, value in kwargs.items():
            if hasattr(course_stat, key):
                setattr(course_stat, key, F(key) + value)

        course_stat.save()
        cls.build_course_stats(user_id, course_id)

    @staticmethod
    def _get_entity_from_type(
        entity_id: str, entity_type: str
    ) -> Union[Comment, CommentThread, None]:
        """Get entity from type."""
        try:
            if entity_type == "Comment":
                return Comment.objects.get(pk=entity_id)
            else:
                return CommentThread.objects.get(pk=entity_id)
        except ObjectDoesNotExist:
            return None

    @classmethod
    def flag_as_abuse(
        cls, user_id: str, entity_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Flag an entity as abuse."""
        user = User.objects.get(pk=user_id)
        entity = cls._get_entity_from_type(
            entity_id, entity_type=kwargs.get("entity_type", "")
        )
        if not entity:
            raise ValueError("Entity doesn't exist.")

        abuse_flaggers = entity.abuse_flaggers
        first_flag_added = False
        if user.pk not in abuse_flaggers:
            AbuseFlagger.objects.create(
                user=user, content=entity, flagged_at=timezone.now()
            )
            first_flag_added = len(abuse_flaggers) == 1
        if first_flag_added:
            cls.update_stats_for_course(user_id, entity.course_id, active_flags=1)
        return entity.to_dict()

    @classmethod
    def un_flag_as_abuse(
        cls, user_id: str, entity_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Unflag an entity as abuse."""
        user = User.objects.get(pk=user_id)
        entity = cls._get_entity_from_type(
            entity_id, entity_type=kwargs.get("entity_type", "")
        )
        if not entity:
            raise ValueError("Entity doesn't exist.")

        has_no_historical_flags = len(entity.historical_abuse_flaggers) == 0
        if user.pk in entity.abuse_flaggers:
            AbuseFlagger.objects.filter(
                user=user,
                content_object_id=entity.pk,
                content_type=entity.content_type,
            ).delete()
            cls.update_stats_after_unflag(
                entity.author.pk,
                entity.pk,
                has_no_historical_flags,
                entity_type=entity.type,
            )

        return entity.to_dict()

    @classmethod
    def un_flag_all_as_abuse(cls, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        """Unflag all users from an entity."""
        entity = cls._get_entity_from_type(
            entity_id, entity_type=kwargs.get("entity_type", "")
        )
        if not entity:
            raise ValueError("Entity doesn't exist.")

        has_no_historical_flags = len(entity.historical_abuse_flaggers) == 0
        historical_abuse_flaggers = list(
            set(entity.historical_abuse_flaggers) | set(entity.abuse_flaggers)
        )
        for flagger_id in historical_abuse_flaggers:
            HistoricalAbuseFlagger.objects.create(
                content=entity,
                user=User.objects.get(pk=flagger_id),
                flagged_at=timezone.now(),
            )
        AbuseFlagger.objects.filter(
            content_object_id=entity.pk, content_type=entity.content_type
        ).delete()
        cls.update_stats_after_unflag(
            entity.author.pk,
            entity.pk,
            has_no_historical_flags,
            entity_type=entity.type,
        )

        return entity.to_dict()

    @classmethod
    def update_stats_after_unflag(
        cls, user_id: str, entity_id: str, has_no_historical_flags: bool, **kwargs: Any
    ) -> None:
        """Update the stats for the course after unflagging an entity."""
        entity = cls._get_entity_from_type(
            entity_id, entity_type=kwargs.get("entity_type", "")
        )
        if not entity:
            raise ObjectDoesNotExist

        first_historical_flag = (
            has_no_historical_flags and not entity.historical_abuse_flaggers
        )
        if first_historical_flag:
            cls.update_stats_for_course(user_id, entity.course_id, inactive_flags=1)

        if not entity.abuse_flaggers:
            cls.update_stats_for_course(user_id, entity.course_id, active_flags=-1)

    @classmethod
    def update_vote(
        cls,
        content_id: str,
        user_id: str,
        vote_type: str = "",
        is_deleted: bool = False,
        **kwargs: Any,
    ) -> bool:
        """
        Update a vote on a thread (either upvote or downvote).

        :param content: The content containing vote data.
        :param user: The user for the user voting.
        :param vote_type: String indicating the type of vote ('up' or 'down').
        :param is_deleted: Boolean indicating if the user is removing their vote (True) or voting (False).
        :return: True if the vote was successfully updated, False otherwise.
        """
        user = User.objects.get(pk=user_id)
        content = cls._get_entity_from_type(
            content_id, entity_type=kwargs.get("entity_type", "")
        )
        if not content:
            raise ValueError("Entity doesn't exist.")

        votes = content.votes
        user_vote = votes.filter(user__pk=user.pk).first()
        if not is_deleted:
            if vote_type not in ["up", "down"]:
                raise ValueError("Invalid vote_type, use ('up' or 'down')")
            if not user_vote:
                vote = 1 if vote_type == "up" else -1
                user_vote = UserVote.objects.create(
                    user=user,
                    content=content,
                    vote=vote,
                    content_type=content.content_type,
                )
            if vote_type == "up":
                user_vote.vote = 1
            else:
                user_vote.vote = -1
            user_vote.save()
            return True
        else:
            if user_vote:
                user_vote.delete()
                return True

        return False

    @classmethod
    def upvote_content(cls, entity_id: str, user_id: str, **kwargs: Any) -> bool:
        """
        Upvotes the specified thread or comment by the given user.

        Args:
            thread (dict): The thread or comment data to be upvoted.
            user (dict): The user who is performing the upvote.

        Returns:
            bool: True if the vote was successfully updated, False otherwise.
        """
        return cls.update_vote(
            entity_id, user_id, vote_type="up", entity_type=kwargs.get("entity_type")
        )

    @classmethod
    def downvote_content(cls, entity_id: str, user_id: str, **kwargs: Any) -> bool:
        """
        Downvotes the specified thread or comment by the given user.

        Args:
            thread (dict): The thread or comment data to be downvoted.
            user (dict): The user who is performing the downvote.

        Returns:
            bool: True if the vote was successfully updated, False otherwise.
        """
        return cls.update_vote(
            entity_id, user_id, vote_type="down", entity_type=kwargs.get("entity_type")
        )

    @classmethod
    def remove_vote(cls, entity_id: str, user_id: str, **kwargs: Any) -> bool:
        """
        Remove the vote (upvote or downvote) from the specified thread or comment for the given user.

        Args:
            thread (dict): The thread or comment data from which the vote should be removed.
            user (dict): The user who is removing their vote.

        Returns:
            bool: True if the vote was successfully removed, False otherwise.
        """
        return cls.update_vote(
            entity_id, user_id, is_deleted=True, entity_type=kwargs.get("entity_type")
        )

    @staticmethod
    def validate_thread_and_user(
        user_id: str, thread_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Validate thread and user.

        Arguments:
            user_id (str): The ID of the user making the request.
            thread_id (str): The ID of the thread.

        Returns:
            tuple[dict[str, Any], dict[str, Any]]: A tuple containing the user and thread data.

        Raises:
            ValueError: If the thread or user is not found.
        """
        try:
            thread = CommentThread.objects.get(pk=int(thread_id))
            user = ForumUser.objects.get(user__pk=user_id)
        except ObjectDoesNotExist as exc:
            raise ValueError("User / Thread doesn't exist") from exc

        return user.to_dict(), thread.to_dict()

    @staticmethod
    def pin_unpin_thread(thread_id: str, action: str) -> None:
        """
        Pin or unpin the thread based on action parameter.

        Arguments:
            thread_id (str): The ID of the thread to pin/unpin.
            action (str): The action to perform ("pin" or "unpin").
        """
        try:
            comment_thread = CommentThread.objects.get(pk=int(thread_id))
        except ObjectDoesNotExist as exc:
            raise ValueError("Thread doesn't exist") from exc
        comment_thread.pinned = action == "pin"
        comment_thread.save()

    @classmethod
    def get_pinned_unpinned_thread_serialized_data(
        cls, user_id: str, thread_id: str, serializer_class: Any
    ) -> dict[str, Any]:
        """
        Return serialized data of pinned or unpinned thread.

        Arguments:
            user (dict[str, Any]): The user who requested the action.
            thread_id (str): The ID of the thread to pin/unpin.

        Returns:
            dict[str, Any]: The serialized data of the pinned/unpinned thread.

        Raises:
            ValueError: If the serialization is not valid.
        """
        user = ForumUser.objects.get(user__pk=user_id)
        updated_thread = CommentThread.objects.get(pk=thread_id)
        user_data = user.to_dict()
        context = {
            "user_id": user_data["_id"],
            "username": user_data["username"],
            "type": "thread",
            "id": thread_id,
        }
        if updated_thread is not None:
            context = {**context, **updated_thread.to_dict()}
        serializer = serializer_class(data=context, backend=cls)
        if not serializer.is_valid():
            raise ValueError(serializer.errors)

        return serializer.data

    @classmethod
    def handle_pin_unpin_thread_request(
        cls, user_id: str, thread_id: str, action: str, serializer_class: Any
    ) -> dict[str, Any]:
        """
        Catches pin/unpin thread request.

        - validates thread and user.
        - pin or unpin the thread based on action parameter.
        - return serialized data of thread.

        Arguments:
            user_id (str): The ID of the user making the request.
            thread_id (str): The ID of the thread to pin/unpin.
            action (str): The action to perform ("pin" or "unpin").

        Returns:
            dict[str, Any]: The serialized data of the pinned/unpinned thread.
        """
        user, _ = cls.validate_thread_and_user(user_id, thread_id)
        cls.pin_unpin_thread(thread_id, action)
        return cls.get_pinned_unpinned_thread_serialized_data(
            user["_id"], thread_id, serializer_class
        )

    @staticmethod
    def get_abuse_flagged_count(thread_ids: list[str]) -> dict[str, int]:
        """
        Retrieves the count of abuse-flagged comments for each thread in the provided list of thread IDs.

        Args:
            thread_ids (list[str]): List of thread IDs to check for abuse flags.

        Returns:
            dict[str, int]: A dictionary mapping thread IDs to their corresponding abuse-flagged comment count.
        """
        abuse_flagger_count_subquery = (
            AbuseFlagger.objects.filter(
                content_type=ContentType.objects.get_for_model(Comment),
                content_object_id=OuterRef("pk"),
            )
            .values("content_object_id")
            .annotate(count=Count("pk"))
            .values("count")
        )

        abuse_flagged_comments = (
            Comment.objects.filter(
                comment_thread__pk__in=thread_ids,
            )
            .annotate(
                abuse_flaggers_count=Subquery(
                    abuse_flagger_count_subquery, output_field=IntegerField()
                )
            )
            .filter(abuse_flaggers_count__gt=0)
        )

        result = {}
        for comment in abuse_flagged_comments:
            thread_pk = str(comment.comment_thread.pk)
            if thread_pk not in result:
                result[thread_pk] = 0
            abuse_flaggers = "abuse_flaggers_count"
            result[thread_pk] += getattr(comment, abuse_flaggers)

        return result

    @staticmethod
    def get_read_states(
        thread_ids: list[str], user_id: str, course_id: str
    ) -> dict[str, list[Any]]:
        """
        Retrieves the read state and unread comment count for each thread in the provided list.

        Args:
            threads (list[dict[str, Any]]): list of threads to check read state for.
            user_id (str): The ID of the user whose read states are being retrieved.
            course_id (str): The course ID associated with the threads.

        Returns:
            dict[str, list[Any]]: A dictionary mapping thread IDs to a list containing
            whether the thread is read and the unread comment count.
        """
        read_states: dict[str, list[Any]] = {}
        if user_id == "":
            return read_states
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return read_states

        threads = CommentThread.objects.filter(pk__in=thread_ids)
        read_state = ReadState.objects.filter(user=user, course_id=course_id).first()
        if not read_state:
            return read_states

        read_dates = read_state.last_read_times

        for thread in threads:
            read_date = read_dates.filter(comment_thread=thread).first()
            if not read_date:
                continue

            last_activity_at = thread.last_activity_at
            is_read = read_date.timestamp >= last_activity_at
            unread_comment_count = (
                Comment.objects.filter(
                    comment_thread=thread, created_at__gte=read_date.timestamp
                )
                .exclude(author__pk=user_id)
                .count()
            )
            read_states[str(thread.pk)] = [is_read, unread_comment_count]

        return read_states

    @staticmethod
    def get_filtered_thread_ids(
        thread_ids: list[str], context: str, group_ids: list[str]
    ) -> set[str]:
        """
        Filters thread IDs based on context and group ID criteria.

        Args:
            thread_ids (list[str]): List of thread IDs to filter.
            context (str): The context to filter by.
            group_ids (list[str]): List of group IDs for group-based filtering.

        Returns:
            set: A set of filtered thread IDs based on the context and group ID criteria.
        """
        context_threads = CommentThread.objects.filter(
            pk__in=thread_ids, context=context
        )
        context_thread_ids = set(thread.pk for thread in context_threads)

        if not group_ids:
            return context_thread_ids

        group_threads = CommentThread.objects.filter(
            Q(group_id__in=group_ids) | Q(group_id__isnull=True),
            id__in=thread_ids,
        )
        group_thread_ids = set(thread.pk for thread in group_threads)

        return context_thread_ids.union(group_thread_ids)

    @staticmethod
    def get_endorsed(thread_ids: list[str]) -> dict[str, bool]:
        """
        Retrieves endorsed status for each thread in the provided list of thread IDs.

        Args:
            thread_ids (list[str]): List of thread IDs to check for endorsement.

        Returns:
            dict[str, bool]: A dictionary of thread IDs to their endorsed status (True if endorsed, False otherwise).
        """
        endorsed_comments = Comment.objects.filter(
            comment_thread__pk__in=thread_ids, endorsed=True
        )

        return {str(comment.comment_thread.pk): True for comment in endorsed_comments}

    @staticmethod
    def get_user_read_state_by_course_id(
        user_id: str, course_id: str
    ) -> dict[str, Any]:
        """
        Retrieves the user's read state for a specific course.

        Args:
            user (dict[str, Any]): The user object containing read states.
            course_id (str): The course ID to filter the user's read state by.

        Returns:
            dict[str, Any]: The user's read state for the specified course, or an empty dictionary if not found.
        """
        user = User.objects.get(pk=int(user_id))
        try:
            read_state = ReadState.objects.get(user=user, course_id=course_id)
        except ObjectDoesNotExist:
            return {}
        return read_state.to_dict()

    @staticmethod
    def get_sort_criteria(sort_key: str) -> list[str]:
        """
        Generate sorting criteria based on the provided key.

        Parameters:
        -----------
        sort_key : str
            Key to determine sort order ("date", "activity", "votes", "comments").

        Returns:
        --------
        list
            List of strings for sorting, including "pinned" and the relevant field,
            optionally adding "created_at" if needed.
        """
        sort_key_mapper = {
            "date": "-created_at",
            "activity": "-last_activity_at",
            "votes": "-votes_point",
            "comments": "-comments_count",
        }
        sort_key = sort_key or "date"
        sort_key = sort_key_mapper.get(sort_key, "")

        if sort_key:
            # only sort order of -1 (descending) is supported.
            sort_criteria = ["-pinned", sort_key]
            if sort_key not in ["-created_at", "-last_activity_at"]:
                sort_criteria.append("-created_at")
            return sort_criteria
        else:
            return []

    # TODO: Make this function modular
    # pylint: disable=too-many-nested-blocks,too-many-statements
    @classmethod
    def handle_threads_query(
        cls,
        comment_thread_ids: list[str],
        user_id: str,
        course_id: str,
        group_ids: list[int],
        author_id: Optional[str],
        thread_type: Optional[str],
        filter_flagged: bool,
        filter_unread: bool,
        filter_unanswered: bool,
        filter_unresponded: bool,
        count_flagged: bool,
        sort_key: str,
        page: int,
        per_page: int,
        context: str = "course",
        raw_query: bool = False,
    ) -> dict[str, Any]:
        """
        Handles complex thread queries based on various filters and returns paginated results.

        Args:
            comment_thread_ids (list[int]): List of comment thread IDs to filter.
            user (User): The user making the request.
            course_id (str): The course ID associated with the threads.
            group_ids (list[int]): List of group IDs for group-based filtering.
            author_id (int): The ID of the author to filter threads by.
            thread_type (str): The type of thread to filter by.
            filter_flagged (bool): Whether to filter threads flagged for abuse.
            filter_unread (bool): Whether to filter unread threads.
            filter_unanswered (bool): Whether to filter unanswered questions.
            filter_unresponded (bool): Whether to filter threads with no responses.
            count_flagged (bool): Whether to include flagged content count.
            sort_key (str): The key to sort the threads by.
            page (int): The page number for pagination.
            per_page (int): The number of threads per page.
            context (str): The context to filter threads by.
            raw_query (bool): Whether to return raw query results without further processing.

        Returns:
            dict[str, Any]: A dictionary containing the paginated thread results and associated metadata.
        """
        mysql_comment_thread_ids: list[int] = []

        for tid in comment_thread_ids:
            try:
                thread_id = int(tid)
                mysql_comment_thread_ids.append(thread_id)
            except ValueError:
                continue

        if user_id is None or user_id == "":
            user = None
        else:
            try:
                user = User.objects.get(pk=int(user_id))
            except User.DoesNotExist as exc:
                raise ValueError("User does not exist") from exc
        # Base query
        base_query = CommentThread.objects.filter(
            pk__in=mysql_comment_thread_ids, context=context
        )

        # Group filtering
        if group_ids:
            base_query = base_query.filter(
                Q(group_id__in=group_ids) | Q(group_id__isnull=True)
            )

        # Author filtering
        if author_id:
            base_query = base_query.filter(author__pk=author_id)
            if user and int(author_id) != user.pk:
                base_query = base_query.filter(
                    anonymous=False, anonymous_to_peers=False
                )

        # Thread type filtering
        if thread_type:
            base_query = base_query.filter(thread_type=thread_type)

        # Flagged content filtering
        if filter_flagged:
            comment_abuse_flaggers = AbuseFlagger.objects.filter(
                content_object_id=OuterRef("pk"),
                content_type=ContentType.objects.get_for_model(Comment),
            )

            flagged_comments = (
                Comment.objects.filter(course_id=course_id)
                .annotate(has_abuse_flaggers=Exists(comment_abuse_flaggers))
                .filter(has_abuse_flaggers=True)
                .values_list("comment_thread_id", flat=True)
            )
            thread_abuse_flaggers = AbuseFlagger.objects.filter(
                content_object_id=OuterRef("pk"),
                content_type=ContentType.objects.get_for_model(CommentThread),
            )

            flagged_threads = (
                CommentThread.objects.filter(course_id=course_id)
                .annotate(has_abuse_flaggers=Exists(thread_abuse_flaggers))
                .filter(has_abuse_flaggers=True)
                .values_list("id", flat=True)
            )

            base_query = base_query.filter(
                pk__in=list(
                    set(mysql_comment_thread_ids) & set(flagged_comments)
                    | set(flagged_threads)
                )
            )

        # Unanswered questions filtering
        if filter_unanswered:
            endorsed_threads = Comment.objects.filter(
                course_id=course_id,
                parent__isnull=True,
                endorsed=True,
            ).values_list("comment_thread_id", flat=True)
            base_query = base_query.filter(
                thread_type="question",
            ).exclude(pk__in=endorsed_threads)

        # Unresponded threads filtering
        if filter_unresponded:
            base_query = base_query.annotate(num_comments=Count("comment")).filter(
                num_comments=0
            )

        base_query = base_query.annotate(
            votes_point=Sum("uservote__vote"),
            comments_count=Count("comment", distinct=True),
        )

        base_query = base_query.annotate(
            votes_point=Sum("uservote__vote", distinct=True),
            comments_count=Count("comment", distinct=True),
        )

        sort_criteria = cls.get_sort_criteria(sort_key)

        comment_threads = (
            base_query.order_by(*sort_criteria) if sort_criteria else base_query
        )
        thread_count = base_query.count()

        if raw_query:
            return {
                "result": [
                    comment_thread.to_dict() for comment_thread in comment_threads
                ]
            }

        if filter_unread and user:
            read_state = cls.get_user_read_state_by_course_id(str(user.pk), course_id)
            read_dates = read_state.get("last_read_times", {})

            threads: list[str] = []
            skipped = 0
            to_skip = (page - 1) * per_page
            has_more = False

            for thread in comment_threads.iterator():
                thread_key = str(thread.pk)
                if (
                    thread_key not in read_dates
                    or read_dates[thread_key] < thread.last_activity_at
                ):
                    if skipped >= to_skip:
                        if len(threads) == per_page:
                            has_more = True
                            break
                        threads.append(thread.pk)
                    else:
                        skipped += 1
            num_pages = page + 1 if has_more else page
        else:
            threads = [thread.pk for thread in comment_threads]
            page = max(1, page)
            start = per_page * (page - 1)
            end = per_page * page
            paginated_collection = threads[start:end]
            threads = list(paginated_collection)
            num_pages = max(1, math.ceil(thread_count / per_page))

        if len(threads) == 0:
            collection = []
        else:
            collection = cls.threads_presentor(
                threads, user_id, course_id, count_flagged
            )

        return {
            "collection": collection,
            "num_pages": num_pages,
            "page": page,
            "thread_count": thread_count,
        }

    @staticmethod
    def prepare_thread(
        thread_id: str,
        is_read: bool,
        unread_count: int,
        is_endorsed: bool,
        abuse_flagged_count: int,
    ) -> dict[str, Any]:
        """
        Prepares thread data for presentation.

        Args:
            thread (dict[str, Any]): The thread data.
            is_read (bool): Whether the thread is read.
            unread_count (int): The count of unread comments.
            is_endorsed (bool): Whether the thread is endorsed.
            abuse_flagged_count (int): The abuse flagged count.

        Returns:
            dict[str, Any]: A dictionary representing the prepared thread data.
        """
        thread = CommentThread.objects.get(pk=thread_id)
        return {
            **thread.to_dict(),
            "type": "thread",
            "read": is_read,
            "unread_comments_count": unread_count,
            "endorsed": is_endorsed,
            "abuse_flagged_count": abuse_flagged_count,
        }

    @classmethod
    def threads_presentor(
        cls,
        thread_ids: list[str],
        user_id: str,
        course_id: str,
        count_flagged: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Presents the threads by preparing them for display.

        Args:
            threads (list[CommentThread]): List of threads to present.
            user (User): The user presenting the threads.
            course_id (str): The course ID associated with the threads.
            count_flagged (bool, optional): Whether to include flagged content count. Defaults to False.

        Returns:
            list[dict[str, Any]]: A list of prepared thread data.
        """
        threads = CommentThread.objects.filter(pk__in=thread_ids)
        read_states = cls.get_read_states(thread_ids, user_id, course_id)
        threads_endorsed = cls.get_endorsed(thread_ids)
        threads_flagged = (
            cls.get_abuse_flagged_count(thread_ids) if count_flagged else {}
        )

        presenters = []
        for thread_id in thread_ids:
            thread = threads.get(id=thread_id)
            is_read, unread_count = read_states.get(
                thread.pk, (False, thread.comment_count)
            )
            is_endorsed = threads_endorsed.get(thread.pk, False)
            abuse_flagged_count = threads_flagged.get(str(thread.pk), 0)
            presenters.append(
                cls.prepare_thread(
                    thread.pk,
                    is_read,
                    unread_count,
                    is_endorsed,
                    abuse_flagged_count,
                )
            )

        return presenters

    @staticmethod
    def get_username_from_id(user_id: str) -> Optional[str]:
        """
        Retrieve the username associated with a given user ID.

        Args:
            _id (int): The unique identifier of the user.

        Returns:
            Optional[str]: The username of the user if found, or None if not.

        """
        try:
            user = User.objects.get(pk=user_id)
        except ObjectDoesNotExist:
            return None
        return user.username

    @staticmethod
    def validate_object(model: str, obj_id: str) -> Any:
        """
        Validates the object if it exists or not.

        Parameters:
            model: The model for which to validate the id.
            id: The ID of the object to validate in the model.
        Response:
            raise exception if object does not exists.
            return object
        """
        modelss = {
            "CommentThread": CommentThread,
            "Comment": Comment,
        }

        try:
            instance = modelss[model].objects.get(pk=int(obj_id))
        except ObjectDoesNotExist as exc:
            raise ObjectDoesNotExist from exc

        return instance.to_dict()

    @staticmethod
    def find_subscribed_threads(
        user_id: str, course_id: Optional[str] = None
    ) -> list[str]:
        """
        Find threads that a user is subscribed to in a specific course.

        Args:
            user_id (str): The ID of the user.
            course_id (str): The ID of the course.

        Returns:
            list: A list of thread ids that the user is subscribed to in the course.
        """
        subscriptions = Subscription.objects.filter(
            subscriber__pk=user_id,
            source_content_type=ContentType.objects.get_for_model(CommentThread),
        )
        thread_ids = [
            str(subscription.source_object_id) for subscription in subscriptions
        ]
        if course_id:
            thread_ids = list(
                CommentThread.objects.filter(
                    pk__in=thread_ids,
                    course_id=course_id,
                ).values_list("pk", flat=True)
            )

        return thread_ids

    @classmethod
    def subscribe_user(
        cls, user_id: str, source_id: str, source_type: str
    ) -> dict[str, Any] | None:
        """Subscribe a user to a source."""
        source = cls._get_entity_from_type(source_id, source_type)
        if source is None:
            return None

        subscription, _ = Subscription.objects.get_or_create(
            subscriber=User.objects.get(pk=int(user_id)),
            source_object_id=source.pk,
            source_content_type=source.content_type,
        )
        return subscription.to_dict()

    @classmethod
    def unsubscribe_user(
        cls, user_id: str, source_id: str, source_type: Optional[str] = ""
    ) -> None:
        """Unsubscribe a user from a source."""
        source = cls._get_entity_from_type(source_id, source_type or "")
        if source is None:
            return

        Subscription.objects.filter(
            subscriber=User.objects.get(pk=int(user_id)),
            source_object_id=source.pk,
            source_content_type=source.content_type,
        ).delete()

    @staticmethod
    def delete_comments_of_a_thread(thread_id: str) -> None:
        """Delete comments of a thread."""
        Comment.objects.filter(comment_thread__pk=thread_id, parent=None).delete()

    @classmethod
    def delete_subscriptions_of_a_thread(cls, thread_id: str) -> None:
        """Delete subscriptions of a thread."""
        source = cls._get_entity_from_type(thread_id, "CommentThread")
        if source is None:
            return

        Subscription.objects.filter(
            source_object_id=source.pk,
            source_content_type=source.content_type,
        ).delete()

    @staticmethod
    def validate_params(
        params: dict[str, Any], user_id: Optional[str] = None
    ) -> Response | None:
        """
        Validate the request parameters.

        Args:
            params (dict): The request parameters.
            user_id (optional[str]): The Id of the user for validation.

        Returns:
            Response: A Response object with an error message if doesn't exist.
        """
        valid_params = [
            "course_id",
            "author_id",
            "thread_type",
            "flagged",
            "unread",
            "unanswered",
            "unresponded",
            "count_flagged",
            "sort_key",
            "page",
            "per_page",
            "request_id",
            "commentable_ids",
            "group_id",
            "group_ids",
        ]
        if not user_id:
            valid_params.append("user_id")

        for key in params:
            if key not in valid_params:
                return Response(
                    {"error": f"Invalid parameter: {key}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if "course_id" not in params:
            return Response(
                {"error": "Missing required parameter: course_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user_id:
            try:
                User.objects.get(pk=user_id)
            except ObjectDoesNotExist:
                return Response(
                    {"error": "User doesn't exist"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return None

    @classmethod
    def get_threads(
        cls,
        params: dict[str, Any],
        user_id: str,
        serializer: Any,
        thread_ids: list[str],
    ) -> dict[str, Any]:
        """get subscribed or all threads of a specific course for a specific user."""
        count_flagged = bool(params.get("count_flagged", False))
        threads = cls.handle_threads_query(
            thread_ids,
            user_id,
            params["course_id"],
            get_group_ids_from_params(params),
            params.get("author_id", ""),
            params.get("thread_type"),
            bool(params.get("flagged", False)),
            bool(params.get("unread", False)),
            bool(params.get("unanswered", False)),
            bool(params.get("unresponded", False)),
            count_flagged,
            params.get("sort_key", ""),
            int(params.get("page", 1)),
            int(params.get("per_page", 100)),
        )
        context: dict[str, Any] = {
            "count_flagged": count_flagged,
            "include_endorsed": True,
            "include_read_state": True,
        }
        if user_id:
            context["user_id"] = user_id
        serializer = serializer(
            threads.pop("collection"), many=True, context=context, backend=cls
        )
        threads["collection"] = serializer.data
        return threads

    @classmethod
    def get_user_voted_ids(cls, user_id: str, vote: str) -> list[str]:
        """Get the IDs of the posts voted by a user."""
        if vote not in ["up", "down"]:
            raise ValueError("Invalid vote type")

        vote_value = 1 if vote == "up" else -1
        voted_ids = UserVote.objects.filter(
            user__pk=user_id, vote=vote_value
        ).values_list("content_object_id", flat=True)
        return list(voted_ids)

    @staticmethod
    def filter_standalone_threads(comment_ids: list[str]) -> list[str]:
        """Filter out standalone threads from the list of threads."""
        comments = Comment.objects.filter(pk__in=comment_ids)
        filtered_threads = [
            comment.comment_thread
            for comment in comments
            if comment.comment_thread.context != "standalone"
        ]
        return [str(thread.pk) for thread in filtered_threads]

    @classmethod
    def user_to_hash(
        cls, user_id: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Converts user data to a hash
        """
        user = User.objects.get(pk=user_id)
        forum_user = ForumUser.objects.get(user__pk=user_id)
        if params is None:
            params = {}

        user_data = forum_user.to_dict()
        hash_data = {}
        hash_data["username"] = user_data["username"]
        hash_data["external_id"] = user_data["external_id"]
        hash_data["id"] = user_data["external_id"]

        if params.get("complete"):
            subscribed_thread_ids = cls.find_subscribed_threads(user_id)
            upvoted_ids = cls.get_user_voted_ids(user_id, "up")
            downvoted_ids = cls.get_user_voted_ids(user_id, "down")
            hash_data.update(
                {
                    "subscribed_thread_ids": subscribed_thread_ids,
                    "subscribed_commentable_ids": [],
                    "subscribed_user_ids": [],
                    "follower_ids": [],
                    "id": user_id,
                    "upvoted_ids": upvoted_ids,
                    "downvoted_ids": downvoted_ids,
                    "default_sort_key": user_data["default_sort_key"],
                }
            )

        if params.get("course_id"):
            threads = CommentThread.objects.filter(
                author=user,
                course_id=params["course_id"],
                anonymous=False,
                anonymous_to_peers=False,
            )
            comments = Comment.objects.filter(
                author=user,
                course_id=params["course_id"],
                anonymous=False,
                anonymous_to_peers=False,
            )
            comment_ids = list(comments.values_list("pk", flat=True))
            if params.get("group_ids"):
                group_threads = threads.filter(
                    group_id__in=params["group_ids"] + [None]
                )
                group_thread_ids = [str(thread.pk) for thread in group_threads]
                threads_count = len(group_thread_ids)
                comment_thread_ids = cls.filter_standalone_threads(comment_ids)

                group_comment_threads = CommentThread.objects.filter(
                    id__in=comment_thread_ids, group_id__in=params["group_ids"] + [None]
                )
                group_comment_thread_ids = [
                    str(thread.pk) for thread in group_comment_threads
                ]
                comments_count = sum(
                    1
                    for comment_thread_id in comment_thread_ids
                    if comment_thread_id in group_comment_thread_ids
                )
            else:
                thread_ids = [str(thread.pk) for thread in threads]
                threads_count = len(thread_ids)
                comment_thread_ids = cls.filter_standalone_threads(comment_ids)
                comments_count = len(comment_thread_ids)

            hash_data.update(
                {
                    "threads_count": threads_count,
                    "comments_count": comments_count,
                }
            )

        return hash_data

    @staticmethod
    def replace_username(user_id: str, username: str) -> None:
        """Replace the username of a Django user."""
        try:
            user = User.objects.get(id=user_id)
            user.username = username
            user.save()
        except User.DoesNotExist as exc:
            raise ValueError("User does not exist") from exc

    @staticmethod
    def unsubscribe_all(user_id: str) -> None:
        """Unsubscribe user from all content."""
        Subscription.objects.filter(subscriber__pk=user_id).delete()

    # Kept method signature same as mongo implementation
    @staticmethod
    def retire_all_content(
        user_id: str, username: str
    ) -> None:  # pylint: disable=W0613
        """Retire all content from user."""
        comments = Comment.objects.filter(author__pk=user_id)
        for comment in comments:
            comment.body = RETIRED_BODY
            comment.save()

        comment_threads = CommentThread.objects.filter(author__pk=user_id)
        for comment_thread in comment_threads:
            comment_thread.body = RETIRED_BODY
            comment_thread.title = RETIRED_TITLE
            comment_thread.save()

    @staticmethod
    def find_or_create_read_state(user_id: str, thread_id: str) -> dict[str, Any]:
        """Find or create user read states."""
        try:
            user = User.objects.get(pk=user_id)
            thread = CommentThread.objects.get(pk=thread_id)
        except (User.DoesNotExist, CommentThread.DoesNotExist) as exc:
            raise ObjectDoesNotExist from exc

        read_state, _ = ReadState.objects.get_or_create(
            user=user, course_id=thread.course_id
        )
        return read_state.to_dict()

    @classmethod
    def mark_as_read(cls, user_id: str, thread_id: str) -> None:
        """Mark thread as read."""
        user = User.objects.get(pk=user_id)
        thread = CommentThread.objects.get(pk=thread_id)
        read_state, _ = ReadState.objects.get_or_create(
            user=user, course_id=thread.course_id
        )

        LastReadTime.objects.update_or_create(
            read_state=read_state,
            comment_thread=thread,
            defaults={
                "timestamp": timezone.now(),
            },
        )

    @staticmethod
    def find_or_create_user_stats(user_id: str, course_id: str) -> dict[str, Any]:
        """Find or create user stats document."""
        user = User.objects.get(pk=user_id)
        try:
            course_stat = CourseStat.objects.get(user=user, course_id=course_id)
            return course_stat.to_dict()
        except CourseStat.DoesNotExist:
            course_stat = CourseStat(
                user=user,
                course_id=course_id,
                active_flags=0,
                inactive_flags=0,
                threads=0,
                responses=0,
                replies=0,
                last_activity_at=None,
            )
            course_stat.save()
            return course_stat.to_dict()

    @staticmethod
    def update_user_stats_for_course(user_id: str, stat: dict[str, Any]) -> None:
        """Update user stats for course."""
        user = User.objects.get(pk=user_id)
        try:
            course_stat = CourseStat.objects.get(user=user, course_id=stat["course_id"])
            for key, value in stat.items():
                setattr(course_stat, key, value)
            course_stat.save()
        except CourseStat.DoesNotExist:
            course_stat = CourseStat(user=user, **stat)
            course_stat.save()

    @classmethod
    def build_course_stats(cls, author_id: str, course_id: str) -> None:
        """Build course stats."""
        author = User.objects.get(pk=author_id)
        threads = CommentThread.objects.filter(
            author=author,
            course_id=course_id,
            anonymous_to_peers=False,
            anonymous=False,
        )
        comments = Comment.objects.filter(
            author=author,
            course_id=course_id,
            anonymous_to_peers=False,
            anonymous=False,
        )

        responses = comments.filter(parent__isnull=True)
        replies = comments.filter(parent__isnull=False)

        comment_ids = [comment.pk for comment in comments]
        threads_ids = [thread.pk for thread in threads]

        active_flags_comments = (
            AbuseFlagger.objects.filter(
                content_object_id__in=comment_ids, content_type=Comment().content_type
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )

        active_flags_threads = (
            AbuseFlagger.objects.filter(
                content_object_id__in=threads_ids,
                content_type=CommentThread().content_type,
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )

        active_flags = active_flags_comments + active_flags_threads

        inactive_flags_comments = (
            HistoricalAbuseFlagger.objects.filter(
                content_object_id__in=comment_ids, content_type=Comment().content_type
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )

        inactive_flags_threads = (
            HistoricalAbuseFlagger.objects.filter(
                content_object_id__in=threads_ids,
                content_type=CommentThread().content_type,
            )
            .values("content_object_id")
            .annotate(count=Count("content_object_id"))
            .count()
        )

        inactive_flags = inactive_flags_comments + inactive_flags_threads

        threads_updated_at = threads.aggregate(Max("updated_at"))["updated_at__max"]
        comments_updated_at = comments.aggregate(Max("updated_at"))["updated_at__max"]

        updated_at = max(
            threads_updated_at or timezone.now() - timedelta(days=365 * 100),
            comments_updated_at or timezone.now() - timedelta(days=365 * 100),
        )

        stats, _ = CourseStat.objects.get_or_create(user=author, course_id=course_id)
        stats.threads = threads.count()
        stats.responses = responses.count()
        stats.replies = replies.count()
        stats.active_flags = active_flags
        stats.inactive_flags = inactive_flags
        stats.last_activity_at = updated_at
        stats.save()
        cls.update_user_stats_for_course(author_id, stats.to_dict())

    @classmethod
    def update_all_users_in_course(cls, course_id: str) -> list[str]:
        """Update all user stats in a course."""
        course_comments = Comment.objects.filter(
            anonymous=False,
            anonymous_to_peers=False,
            course_id=course_id,
        )
        course_threads = CommentThread.objects.filter(
            anonymous=False,
            anonymous_to_peers=False,
            course_id=course_id,
        )

        comment_authors = set(course_comments.values_list("author__id", flat=True))
        thread_authors = set(course_threads.values_list("author__id", flat=True))
        author_ids = list(comment_authors | thread_authors)

        for author_id in author_ids:
            cls.build_course_stats(author_id, course_id)
        return author_ids

    @staticmethod
    def get_user_by_username(username: str | None) -> dict[str, Any] | None:
        """Return user from username."""
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return None
        try:
            forum_user = ForumUser.objects.get(user=user)
        except ForumUser.DoesNotExist:
            return None
        return forum_user.to_dict()

    @staticmethod
    def generate_id() -> str:
        """Generate a random id."""
        return str(random.randint(1, 1000000))

    @staticmethod
    def find_or_create_user(
        user_id: str,
        username: Optional[str] = None,
        default_sort_key: Optional[str] = "date",
    ) -> str:
        """Find or create user."""
        username = username or user_id
        try:
            user = User.objects.get(pk=int(user_id))
        except User.DoesNotExist:
            user = None

        if user is None:
            if User.objects.filter(username=username).exists():
                raise ValueError(f"User with username {username} already exists")
            user = User.objects.create(pk=int(user_id), username=username)

        forum_user, _ = ForumUser.objects.get_or_create(
            user=user, defaults={"default_sort_key": default_sort_key}
        )
        return forum_user.user.pk

    @staticmethod
    def get_comment(comment_id: str) -> dict[str, Any] | None:
        """Return comment from comment_id."""
        try:
            comment = Comment.objects.get(pk=comment_id)
        except Comment.DoesNotExist:
            return None
        return comment.to_dict()

    @staticmethod
    def get_comments(**kwargs: Any) -> list[dict[str, Any]]:
        """Return comments from kwargs."""
        return Comment.get_list(**kwargs)

    @staticmethod
    def get_comments_count(**kwargs: Any) -> int:
        """Return comments from kwargs."""
        return Comment.get_list_total_count(**kwargs)

    @staticmethod
    def update_child_count_in_parent_comment(parent_id: str, count: int) -> None:
        """
        Update(increment/decrement) child_count in parent comment.

        Args:
            parent_id: The ID of the parent comment whose child_count will be updated.
            count: It can be any number.
                If positive, this function will increase child_count by the count.
                If negative, this function will decrease child_count by the count.

        Returns:
            None.
        """
        Comment.objects.filter(pk=int(parent_id)).update(
            child_count=F("child_count") + count
        )

    @classmethod
    def create_comment(cls, data: dict[str, Any]) -> str:
        """Handle comment creation and returns a comment."""
        comment_thread = None
        parent = None
        comment_thread_id = data.get("comment_thread_id")
        parent_id = data.get("parent_id")
        if comment_thread_id:
            comment_thread = CommentThread.objects.get(pk=int(comment_thread_id))
        if parent_id:
            parent = Comment.objects.get(pk=int(parent_id))
        new_comment = Comment.objects.create(
            body=data.get("body"),
            course_id=data.get("course_id"),
            anonymous=data.get("anonymous", False),
            anonymous_to_peers=data.get("anonymous_to_peers", False),
            author=User.objects.get(pk=int(data["author_id"])),
            comment_thread=comment_thread,
            parent=parent,
            depth=data.get("depth", 0),
        )
        new_comment.sort_key = new_comment.get_sort_key()
        new_comment.save()
        if data.get("parent_id"):
            cls.update_child_count_in_parent_comment(data["parent_id"], 1)
            cls.update_stats_for_course(data["author_id"], data["course_id"], replies=1)
        else:
            cls.update_stats_for_course(
                data["author_id"], data["course_id"], responses=1
            )
        return str(new_comment.pk)

    @classmethod
    def delete_comment(cls, comment_id: str) -> None:
        """Delete comment from comment_id."""
        comment = Comment.objects.get(pk=comment_id)
        if comment.parent:
            cls.update_child_count_in_parent_comment(str(comment.parent.pk), -1)

        comment.delete()

    @staticmethod
    def get_commentables_counts_based_on_type(course_id: str) -> dict[str, Any]:
        """Return commentables counts in a course based on thread's type."""
        result = (
            CommentThread.objects.filter(course_id=course_id)
            .values("commentable_id")
            .annotate(
                discussion_count=Count(
                    Case(
                        When(thread_type="discussion", then=1),
                        output_field=IntegerField(),
                    )
                ),
                question_count=Count(
                    Case(
                        When(thread_type="question", then=1),
                        output_field=IntegerField(),
                    )
                ),
            )
            .order_by()
        )
        commentable_counts = {}
        for commentable in result:
            topic_id = commentable["commentable_id"]
            commentable_counts[topic_id] = {
                "discussion": commentable["discussion_count"],
                "question": commentable["question_count"],
            }
        return commentable_counts

    @staticmethod
    def update_comment(comment_id: str, **kwargs: Any) -> int:
        """Updates a comment in the database."""
        try:
            comment = Comment.objects.get(id=comment_id)
        except Comment.DoesNotExist:
            return 0

        if kwargs.get("body"):
            comment.body = kwargs["body"]
        if kwargs.get("course_id"):
            comment.course_id = kwargs["course_id"]
        if kwargs.get("anonymous"):
            comment.anonymous = kwargs["anonymous"]
        if kwargs.get("anonymous_to_peers"):
            comment.anonymous_to_peers = kwargs["anonymous_to_peers"]
        if kwargs.get("comment_thread_id"):
            comment.comment_thread = CommentThread.objects.get(
                pk=kwargs["comment_thread_id"]
            )
        if kwargs.get("visible"):
            comment.visible = kwargs["visible"]
        if kwargs.get("author_id"):
            comment.author = User.objects.get(pk=kwargs["author_id"])
        if kwargs.get("endorsed"):
            comment.endorsed = kwargs["endorsed"]
        if kwargs.get("child_count"):
            comment.child_count = kwargs["child_count"]
        if kwargs.get("depth"):
            comment.depth = kwargs["depth"]

        if kwargs.get("endorsed") and kwargs.get("endorsement_user_id"):
            comment.endorsement = {
                "user_id": kwargs["endorsement_user_id"],
                "time": timezone.now(),
            }
        else:
            comment.endorsement = {}

        if "abuse_flaggers" in kwargs:
            existing_abuse_flaggers = AbuseFlagger.objects.filter(
                content_object_id=comment.pk,
                content_type=comment.content_type,
            ).values_list("user_id", flat=True)

            new_abuse_flaggers = [
                int(user_id)
                for user_id in kwargs["abuse_flaggers"]
                if int(user_id) not in existing_abuse_flaggers
            ]

            for user_id in new_abuse_flaggers:
                AbuseFlagger.objects.create(
                    user=User.objects.get(pk=user_id),
                    content_object_id=comment.pk,
                    content_type=comment.content_type,
                )

        if "historical_abuse_flaggers" in kwargs:
            existing_historical_abuse_flaggers = HistoricalAbuseFlagger.objects.filter(
                content_object_id=comment.pk,
                content_type=comment.content_type,
            ).values_list("user_id", flat=True)

            new_historical_abuse_flaggers = [
                int(user_id)
                for user_id in kwargs["historical_abuse_flaggers"]
                if int(user_id) not in existing_historical_abuse_flaggers
            ]
            HistoricalAbuseFlagger.objects.bulk_create(
                [
                    HistoricalAbuseFlagger(
                        user=User.objects.get(pk=user_id),
                        content_object_id=comment.pk,
                        content_type=comment.content_type,
                    )
                    for user_id in new_historical_abuse_flaggers
                ]
            )

        if kwargs.get("editing_user_id"):
            EditHistory.objects.create(
                comment=comment,
                author=User.objects.get(pk=kwargs["editing_user_id"]),
                original_body=kwargs.get("original_body"),
                reason_code=kwargs.get("edit_reason_code"),
                created_at=timezone.now(),
            )

        if "votes" in kwargs:
            up_votes = kwargs["votes"].get("up", [])
            down_votes = kwargs["votes"].get("down", [])
            for user_id in up_votes:
                UserVote.objects.update_or_create(
                    user=User.objects.get(id=int(user_id)),
                    content_type=comment.content_type,
                    content_object_id=comment.pk,
                    vote=1,
                )
            for user_id in down_votes:
                UserVote.objects.update_or_create(
                    user=User.objects.get(id=int(user_id)),
                    content_type=comment.content_type,
                    content_object_id=comment.pk,
                    vote=-1,
                )

        if "votes" in kwargs:
            up_votes = kwargs["votes"].get("up", [])
            down_votes = kwargs["votes"].get("down", [])
            for user_id in up_votes:
                UserVote.objects.update_or_create(
                    user=User.objects.get(id=int(user_id)),
                    content_type=comment.content_type,
                    content_object_id=comment.pk,
                    vote=1,
                )
            for user_id in down_votes:
                UserVote.objects.update_or_create(
                    user=User.objects.get(id=int(user_id)),
                    content_type=comment.content_type,
                    content_object_id=comment.pk,
                    vote=-1,
                )

        comment.updated_at = timezone.now()
        comment.save()
        return 1

    @staticmethod
    def get_thread_id_from_comment(comment_id: str) -> dict[str, Any] | None:
        """Return thread_id from comment_id."""
        comment = Comment.objects.get(pk=comment_id)
        if comment.comment_thread:
            return comment.comment_thread.to_dict()
        raise ValueError("Comment doesn't have the thread.")

    @staticmethod
    def get_user(user_id: str) -> dict[str, Any] | None:
        """Return user from user_id."""
        try:
            return ForumUser.objects.get(user__pk=int(user_id)).to_dict()
        except ObjectDoesNotExist:
            return None

    @staticmethod
    def get_thread(thread_id: str) -> dict[str, Any] | None:
        """Return thread from thread_id."""
        try:
            thread = CommentThread.objects.get(pk=thread_id)
        except CommentThread.DoesNotExist:
            return None
        return thread.to_dict()

    @classmethod
    def get_subscription(
        cls, subscriber_id: str, source_id: str, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Return subscription from subscriber_id and source_id."""
        source = cls._get_entity_from_type(
            source_id, entity_type=kwargs.get("source_type", "")
        )
        if not source:
            return None
        try:
            subscription = Subscription.objects.get(
                subscriber_id=User.objects.get(pk=int(subscriber_id)),
                source_object_id=source.pk,
                source_content_type=source.content_type,
            )
        except Subscription.DoesNotExist:
            return None
        return subscription.to_dict()

    @classmethod
    def get_subscriptions(cls, query: dict[str, Any]) -> list[dict[str, Any]]:
        """Return subscriptions from filter."""
        source = cls._get_entity_from_type(
            entity_id=query["source_id"], entity_type=query.get("source_type", "")
        )
        if not source:
            return []

        subscriptions = (
            Subscription.objects.filter(
                source_object_id=source.pk,
                source_content_type=source.content_type,
            )
            .distinct()
            .order_by("subscriber_id", "source_object_id")
        )

        return [subscription.to_dict() for subscription in subscriptions]

    @staticmethod
    def delete_thread(thread_id: str) -> int:
        """Delete thread from thread_id."""
        try:
            thread = CommentThread.objects.get(pk=thread_id)
        except ObjectDoesNotExist:
            return 0
        thread.delete()
        return 1

    @staticmethod
    def create_thread(data: dict[str, Any]) -> str:
        """Create thread."""
        optional_args = {}
        if group_id := data.get("group_id"):
            optional_args["group_id"] = group_id
        new_thread = CommentThread.objects.create(
            title=data["title"],
            body=data["body"],
            course_id=data["course_id"],
            anonymous=data.get("anonymous", False),
            anonymous_to_peers=data.get("anonymous_to_peers", False),
            author=User.objects.get(pk=int(data["author_id"])),
            commentable_id=data.get("commentable_id", "course"),
            thread_type=data.get("thread_type", "discussion"),
            context=data.get("context", "course"),
            last_activity_at=timezone.now(),
            **optional_args,
        )
        return str(new_thread.pk)

    @staticmethod
    def update_thread(
        thread_id: str,
        **kwargs: Any,
    ) -> int:
        """Updates a thread document in the database."""
        thread = CommentThread.objects.get(id=thread_id)

        if "thread_type" in kwargs:
            thread.thread_type = kwargs["thread_type"]
        if "title" in kwargs:
            thread.title = kwargs["title"]
        if "body" in kwargs:
            thread.body = kwargs["body"]
        if "course_id" in kwargs:
            thread.course_id = kwargs["course_id"]
        if "anonymous" in kwargs:
            thread.anonymous = kwargs["anonymous"]
        if "anonymous_to_peers" in kwargs:
            thread.anonymous_to_peers = kwargs["anonymous_to_peers"]
        if "commentable_id" in kwargs:
            thread.commentable_id = kwargs["commentable_id"]
        if "author_id" in kwargs and kwargs["author_id"]:
            thread.author = User.objects.get(pk=int(kwargs["author_id"]))
        if "closed_by_id" in kwargs and kwargs["closed_by_id"]:
            thread.closed_by = User.objects.get(pk=int(kwargs["closed_by_id"]))
        if "pinned" in kwargs:
            thread.pinned = kwargs["pinned"]
        if "close_reason_code" in kwargs:
            thread.close_reason_code = kwargs["close_reason_code"]
        if "closed" in kwargs:
            thread.closed = kwargs["closed"]
            if not kwargs["closed"]:
                thread.closed_by = None  # type: ignore
                thread.close_reason_code = None
        if "endorsed" in kwargs:
            thread.endorsed = kwargs["endorsed"]
        if "group_id" in kwargs:
            thread.group_id = kwargs["group_id"]
        if "abuse_flaggers" in kwargs:
            existing_abuse_flaggers = AbuseFlagger.objects.filter(
                content_object_id=thread.pk,
                content_type=thread.content_type,
            ).values_list("user_id", flat=True)

            new_abuse_flaggers = [
                int(user_id)
                for user_id in kwargs["abuse_flaggers"]
                if int(user_id) not in existing_abuse_flaggers
            ]

            for user_id in new_abuse_flaggers:
                AbuseFlagger.objects.create(
                    user=User.objects.get(pk=user_id),
                    content_object_id=thread.pk,
                    content_type=thread.content_type,
                )

        if "historical_abuse_flaggers" in kwargs:
            existing_historical_abuse_flaggers = HistoricalAbuseFlagger.objects.filter(
                content_object_id=thread.pk,
                content_type=thread.content_type,
            ).values_list("user__pk", flat=True)

            new_historical_abuse_flaggers = [
                int(user_id)
                for user_id in kwargs["historical_abuse_flaggers"]
                if int(user_id) not in existing_historical_abuse_flaggers
            ]

            HistoricalAbuseFlagger.objects.bulk_create(
                [
                    HistoricalAbuseFlagger(
                        user=User.objects.get(pk=user_id),
                        content_object_id=thread.pk,
                        content_type=thread.content_type,
                    )
                    for user_id in new_historical_abuse_flaggers
                ]
            )

        if "editing_user_id" in kwargs and kwargs["editing_user_id"]:
            EditHistory.objects.create(
                content_object_id=thread.pk,
                content_type=thread.content_type,
                reason_code=kwargs.get("edit_reason_code"),
                original_body=kwargs.get("original_body"),
                editor=User.objects.get(pk=kwargs["editing_user_id"]),
                created_at=timezone.now(),
            )

        if "votes" in kwargs:
            up_votes = kwargs["votes"].get("up", [])
            down_votes = kwargs["votes"].get("down", [])
            for user_id in up_votes:
                UserVote.objects.update_or_create(
                    user=User.objects.get(id=int(user_id)),
                    content_type=thread.content_type,
                    content_object_id=thread.pk,
                    vote=1,
                )
            for user_id in down_votes:
                UserVote.objects.update_or_create(
                    user=User.objects.get(id=int(user_id)),
                    content_type=thread.content_type,
                    content_object_id=thread.pk,
                    vote=-1,
                )

        thread.updated_at = timezone.now()
        thread.save()
        return 1

    @staticmethod
    def get_user_thread_filter(course_id: str) -> dict[str, Any]:
        """Get user thread filter"""
        return {"course_id": course_id}

    @staticmethod
    def get_filtered_threads(query: dict[str, Any]) -> list[dict[str, Any]]:
        """Return a list of threads that match the given filter."""
        threads = CommentThread.objects.filter(**query)
        return [thread.to_dict() for thread in threads]

    @staticmethod
    def update_user(user_id: str, data: dict[str, Any]) -> int:
        """
        Updates user info and ForumUser fields.

        Args:
            user_id: ID of the user to update.
            data: Dictionary containing updated user info and ForumUser fields.
        """
        try:
            user = User.objects.get(id=user_id)
            forum_user = ForumUser.objects.get(user=user)
        except ObjectDoesNotExist:
            return 0

        if "username" in data:
            user.username = data["username"]
        if "email" in data:
            user.email = data["email"]
        if "default_sort_key" in data:
            forum_user.default_sort_key = data["default_sort_key"]
        if "read_states" in data and data["read_states"] == []:
            user_read_states = ReadState.objects.filter(user=user)
            user_read_states.delete()

        user.save()
        forum_user.save()
        return 1

    @staticmethod
    def replace_username_in_all_content(user_id: str, username: str) -> None:
        """Replace the username of a Django user."""
        try:
            user = User.objects.get(pk=user_id)
            user.username = username
            user.save()
        except User.DoesNotExist as exc:
            raise ValueError("User does not exist") from exc

    @staticmethod
    def get_thread_id_by_comment_id(parent_comment_id: str) -> str:
        """
        The thread Id from the parent comment.
        """
        try:
            comment = Comment.objects.get(pk=parent_comment_id)
        except ObjectDoesNotExist as exc:
            raise ValueError("comment does not exist.") from exc
        return comment.comment_thread.pk

    @staticmethod
    def update_comment_and_get_updated_comment(
        comment_id: str,
        body: Optional[str] = None,
        course_id: Optional[str] = None,
        user_id: Optional[str] = None,
        anonymous: Optional[bool] = False,
        anonymous_to_peers: Optional[bool] = False,
        endorsed: Optional[bool] = None,
        closed: Optional[bool] = False,
        editing_user_id: Optional[str] = None,
        edit_reason_code: Optional[str] = None,
        endorsement_user_id: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """
        Update an existing child/parent comment.

        Parameters:
            comment_id: The ID of the comment to be edited.
            body (Optional[str]): The content of the comment.
            course_id (Optional[str]): The Id of the respective course.
            user_id (Optional[str]): The requesting user id.
            anonymous (Optional[bool]): anonymous flag(True or False).
            anonymous_to_peers (Optional[bool]): anonymous to peers flag(True or False).
            endorsed (Optional[bool]): Flag indicating if the comment is endorsed by any user.
            closed (Optional[bool]): Flag indicating if the comment thread is closed.
            editing_user_id (Optional[str]): The ID of the user editing the comment.
            edit_reason_code (Optional[str]): The reason for editing the comment, typically represented by a code.
            endorsement_user_id (Optional[str]): The ID of the user endorsing the comment.
        Response:
            The details of the comment that is updated.
        """
        try:
            comment = Comment.objects.get(id=comment_id)
        except Comment.DoesNotExist:
            return None

        original_body = comment.body
        if body:
            comment.body = body
        if course_id:
            comment.course_id = course_id
        if user_id:
            comment.author = User.objects.get(pk=user_id)
        if anonymous is not None:
            comment.anonymous = anonymous
        if anonymous_to_peers is not None:
            comment.anonymous_to_peers = anonymous_to_peers
        if endorsed is not None:
            comment.endorsed = endorsed
            if endorsed is False:
                comment.endorsement = {}
            if endorsement_user_id:
                comment.endorsement = {
                    "user_id": endorsement_user_id,
                    "time": str(timezone.now()),
                }

        if editing_user_id:
            EditHistory.objects.create(
                content_object_id=comment.pk,
                content_type=comment.content_type,
                editor=User.objects.get(pk=editing_user_id),
                original_body=original_body,
                reason_code=edit_reason_code,
                created_at=timezone.now(),
            )

        comment.updated_at = timezone.now()
        comment.save()
        return comment.to_dict()

    @staticmethod
    def get_course_id_by_thread_id(thread_id: str) -> str | None:
        """
        Return course_id for the matching thread.
        """
        thread = CommentThread.objects.filter(id=thread_id).first()
        if thread:
            return thread.course_id
        return None

    @staticmethod
    def get_course_id_by_comment_id(comment_id: str) -> str | None:
        """
        Return course_id for the matching comment.
        """
        comment = Comment.objects.filter(id=comment_id).first()
        if comment:
            return comment.course_id
        return None

    @staticmethod
    def get_users(**kwargs: Any) -> list[dict[str, Any]]:
        """
        Retrieves a list of users in the database based on provided filters.

        Args:
            kwargs: The filter arguments.

        Returns:
            A list of users.
        """
        forum_users = ForumUser.objects.filter(**kwargs)
        sort_key = kwargs.get("sort_key")
        if sort_key:
            forum_users = forum_users.order_by(sort_key)

        result = [user.to_dict() for user in forum_users]
        return result

    @staticmethod
    def get_user_sort_criterion(sort_by: str) -> dict[str, Any]:
        """
        Get sort criterion based on sort_by parameter.

        Args:
            sort_by (str): The sort_by parameter.

        Returns:
            A dictionary representing the sort criterion.
        """
        if sort_by == "flagged":
            return {
                "course_stats__active_flags": -1,
                "course_stats__inactive_flags": -1,
                "username": -1,
            }
        elif sort_by == "recency":
            return {"course_stats__last_activity_at": -1, "username": -1}
        else:
            return {
                "course_stats__threads": -1,
                "course_stats__responses": -1,
                "course_stats__replies": -1,
                "username": -1,
            }

    @classmethod
    def get_paginated_user_stats(
        cls, course_id: str, page: int, per_page: int, sort_criterion: dict[str, Any]
    ) -> dict[str, Any]:
        """Get paginated user stats."""
        users = User.objects.filter(
            Q(course_stats__course_id=course_id)
            & Q(course_stats__course_id__isnull=False)
        ).order_by(
            *[f"-{key}" for key, value in sort_criterion.items() if value == -1],
            *[key for key, value in sort_criterion.items() if value == 1],
        )

        paginator = Paginator(users, per_page)
        paginated_users = paginator.page(page)

        forum_users = [
            ForumUser.objects.get(user_id=user_id)
            for user_id in paginated_users.object_list
        ]
        return {
            "pagination": [{"total_count": paginator.count}],
            "data": [user.to_dict(course_id=course_id) for user in forum_users],
        }

    @staticmethod
    def get_contents(**kwargs: Any) -> list[dict[str, Any]]:
        """
        Retrieves a list of comments and comment threads in the database based on provided filters.

        Args:
            kwargs: The filter arguments.

        Returns:
            A list of comments and comment threads.
        """
        comment_filters = {
            key: value for key, value in kwargs.items() if hasattr(Comment, key)
        }
        thread_filters = {
            key: value for key, value in kwargs.items() if hasattr(CommentThread, key)
        }

        comments = Comment.objects.filter(**comment_filters)
        threads = CommentThread.objects.filter(**thread_filters)

        sort_key = kwargs.get("sort_key")
        if sort_key:
            comments = comments.order_by(sort_key)
            threads = threads.order_by(sort_key)

        result = [content.to_dict() for content in list(comments) + list(threads)]
        return result

    @staticmethod
    def find_thread(**kwargs: Any) -> Optional[dict[str, Any]]:
        """
        Retrieves a first matching thread from the database.
        """
        thread = CommentThread.objects.filter(**kwargs).first()
        return thread.to_dict() if thread else None

    @staticmethod
    def find_comment(
        is_parent_comment: bool = True, with_abuse_flaggers: bool = False, **kwargs: Any
    ) -> Optional[dict[str, Any]]:
        """
        Retrieves a first matching thread from the database.
        """
        if is_parent_comment:
            kwargs["parent__isnull"] = True
        else:
            kwargs["parent__isnull"] = False

        comments = Comment.objects.filter(**kwargs)
        comment = None
        if with_abuse_flaggers:
            for comm in comments:
                if comm.abuse_flaggers:
                    comment = comm
                    break
        else:
            comment = comments.first()

        return comment.to_dict() if comment else None

    @staticmethod
    def get_user_contents_by_username(username: str) -> list[dict[str, Any]]:
        """
        Retrieve all threads and comments authored by a specific user.
        """
        contents = [
            comment.to_dict()
            for comment in Comment.objects.filter(author__username=username)
        ] + [
            thread.to_dict()
            for thread in CommentThread.objects.filter(author__username=username)
        ]
        return contents
