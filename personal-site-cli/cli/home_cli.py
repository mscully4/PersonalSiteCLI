from typing import List, Set
from .base_cli import BaseCLI
from attrs import asdict
from utils.cli_utils import (
    clr_line,
    cls,
    get_input,
    get_selection,
    print_figlet,
    print_single_list,
)
from utils.constants import (
    APP_NAME,
)
from clients import DDBClient, GooglePhotosClient, S3Client, Namespaces, HomeEntities
from utils.photo_processing import (
    IMAGE_TYPE,
    download_image,
    hash_buffer_md5,
    rescale_image,
    save_image_to_buffer,
)
from utils.navigation import MenuAction
from models.home import Photo
from PIL import Image


class HomeCLI(BaseCLI):
    PHOTO_PK = f"{Namespaces.HOME}#{HomeEntities.PHOTO}"
    MAX_PHOTO_SIZE = 1024

    def __init__(
        self,
        google_photos_client: GooglePhotosClient,
        s3_client: S3Client,
        ddb_client: DDBClient,
    ):
        self.s3_client = s3_client
        self.ddb_client = ddb_client
        self.google_photos_client = google_photos_client

        self._run = False
        self._menu_actions: List[MenuAction] = [
            MenuAction("Update Photos", self.update_photos, is_async=True),
        ]

    def _print_menu(self):
        """
        A method that prints the menu options for the CLI
        """

        cls()

        print_figlet(APP_NAME)
        print("Travel Menu")

        print()

        print("0. To Exit")
        for i, action in enumerate(self._menu_actions):
            print(f"{i+1}. {action.name}")

        print()

    async def run(self) -> None:
        """
        A method for performing a task in the Home CLI
        """
        self._run = True

        while self._run:
            self._print_menu()
            sel = get_selection(1, len(self._menu_actions), allowed_chars=[])

            if sel == 0:
                self._run = False
                return

            action = self._menu_actions[sel - 1]
            if action.is_async:
                await action.command()
            else:
                action.command()

    async def update_photos(self):
        """
        A method for updating the photos on the home page
        """
        print_figlet(APP_NAME)

        inp = get_input(
            "Enter the album name to use the autocomplete functionality",
        )

        # Album information has to be loaded from Google Photos.  If the loading process isn't done, wait for it.
        if not self.google_photos_client.done:
            await self.google_photos_client.albums

        print()

        # Fuzzy match input against existing Google Photos albums
        suggestions = self.google_photos_client.get_album_suggestions(
            self.google_photos_client.albums.result(), inp, 5
        )

        print_single_list([sug[0] for sug in suggestions])

        print()
        sel = get_selection(0, len(suggestions), []) - 1

        data = self.google_photos_client.get_album_info(suggestions[sel][1])
        self._process_photos(data["id"])

    def _get_existing_photos(self) -> Set[str]:
        """
        A method for getting the existing Home page photos
        """
        existing = self.ddb_client.get_equals(self.PHOTO_PK)
        return set([image["hsh"] for image in existing])

    def _process_photos(self, album_id: str) -> None:
        """
        A method for retrieving a photo list from GP, downloading/editing the
        photos, uploading them to S3 and writing the info to DDB
        """
        print_figlet(APP_NAME)
        photos = self.google_photos_client.get_album_photos(album_id)

        existing = self._get_existing_photos()

        for i, obj in enumerate(photos):
            print(f"Uploading Photo: {i + 1} out of {len(photos)}")
            img: Image.Image = download_image(obj["baseUrl"] + "=d")
            img = rescale_image(img, self.MAX_PHOTO_SIZE)
            buffer = save_image_to_buffer(img)
            hsh = hash_buffer_md5(buffer)
            if hsh in existing:
                clr_line()
                continue

            file_path = f"{Namespaces.HOME}/{hsh}.{IMAGE_TYPE}"
            s3_path = self.s3_client.write_image_to_s3(
                file_path, buffer, ACL="public-read", ContentType=f"image/{IMAGE_TYPE}"
            )

            photo = Photo(
                photo_id=obj["id"],
                src=s3_path,
                height=img.height,
                width=img.width,
                creation_timestamp=obj["mediaMetadata"]["creationTime"],
                hsh=hsh,
            )
            self.ddb_client.put(self.PHOTO_PK, hsh, asdict(photo))
            clr_line()
