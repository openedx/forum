"""Management command for creating mongodb indexes"""

from django.core.management.base import BaseCommand

from forum.backends.mongodb import BaseContents


class Command(BaseCommand):
    """
    Django management command for creating mongodb indexes.
    """

    help = "Create or Update indexes in the mongodb for the content model"

    def handle(self, *args: list[str], **kwargs: dict[str, str]) -> None:
        """
        Handles the execution of the forum_create_mongodb_indexes command.

        This command creates or updates indexes in the mongodb for the content model.
        """
        BaseContents().create_indexes()
        self.stdout.write(
            self.style.SUCCESS("Created/Updated Mongodb indexes successfully.")
        )
