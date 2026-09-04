from typing import List, Set
from .base_cli import BaseCLI
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
from clients import AmplifyClient, ImmichClient, S3Client, home_photo_item
from utils.photo_processing import (
    IMAGE_TYPE,
    hash_buffer_md5,
    image_from_bytes,
    rescale_image,
    save_image_to_buffer,
)
from utils.navigation import MenuAction, MenuNavigationUserCommands
from models.home import Photo
from PIL import Image


class HomeCLI(BaseCLI):
    MAX_PHOTO_SIZE = 1024

    def __init__(
        self,
        immich_client: ImmichClient,
        s3_client: S3Client,
        amplify_client: AmplifyClient,
    ):
        self.s3_client = s3_client
        self.amplify = amplify_client
        self.immich_client = immich_client

        self._run = False
        self._menu_actions: List[MenuAction] = [
            MenuAction("Update Photos", self.update_photos),
        ]

    def _print_menu(self):
        """
        A method that prints the menu options for the CLI
        """

        cls()

        print_figlet(APP_NAME)
        print("Home Menu")

        print()

        print("0. To Exit")
        for i, action in enumerate(self._menu_actions):
            print(f"{i+1}. {action.name}")

        print()

    def run(self) -> None:
        """
        A method for performing a task in the Home CLI
        """
        self._run = True

        while self._run:
            self._print_menu()
            sel = get_selection(0, len(self._menu_actions), allowed_chars=[])

            if sel <= 0:
                self._run = False
                return

            action = self._menu_actions[sel - 1]
            action.command()

    def update_photos(self):
        """
        A method for updating the photos on the home page
        """
        print_figlet(APP_NAME)

        inp = get_input(
            "Enter the album name to use the autocomplete functionality",
        )

        print()

        # Fuzzy match input against existing Immich albums
        suggestions = self.immich_client.get_album_suggestions(
            self.immich_client.get_albums(), inp, 5
        )

        print_single_list([sug[0] for sug in suggestions])

        print()
        sel = get_selection(
            1,
            len(suggestions),
            allowed_chars=[
                MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                MenuNavigationUserCommands.GO_BACK,
            ],
        )

        if sel < 0:
            cls()
            return

        data = self.immich_client.get_album_info(suggestions[sel - 1][1])
        self._process_photos(data["id"])

    def _get_existing_photos(self) -> Set[str]:
        """
        A method for getting the existing Home page photos
        """
        existing = self.amplify.get_home_photos()
        return set([image["hsh"] for image in existing])

    def _process_photos(self, album_id: str) -> None:
        """
        A method for retrieving a photo list from GP, downloading/editing the
        photos, uploading them to S3 and writing the info to DDB
        """
        print_figlet(APP_NAME)
        photos = self.immich_client.get_album_photos(album_id)

        existing = self._get_existing_photos()

        for i, obj in enumerate(photos):
            print(f"Uploading Photo: {i + 1} out of {len(photos)}")
            img: Image.Image = image_from_bytes(self.immich_client.download_asset(obj["id"]))
            img = rescale_image(img, self.MAX_PHOTO_SIZE)
            buffer = save_image_to_buffer(img)
            hsh = hash_buffer_md5(buffer)
            if hsh in existing:
                clr_line()
                continue

            file_path = f"HOME/{hsh}.{IMAGE_TYPE}"
            s3_path = self.s3_client.write_image_to_s3(
                file_path, buffer, ContentType=f"image/{IMAGE_TYPE}"
            )

            photo = Photo(
                photo_id=obj["id"],
                src=s3_path,
                height=img.height,
                width=img.width,
                creation_timestamp=self.immich_client.asset_timestamp(obj),
                hsh=hsh,
            )
            self.amplify.put_home_photo(home_photo_item(photo))
            clr_line()
