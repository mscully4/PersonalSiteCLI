from io import BytesIO
from typing import Dict, List, Optional, Set

from clients import (
    DDBClient,
    GoogleMapsClient,
    ImmichClient,
    Namespaces,
    S3Client,
    TravelEntities,
)
from exceptions import InvalidStateException
from models.google_maps import GeocodedDestination, GeocodedPlace
from models.travel import Album, Destination, Photo, Place
from PIL import Image
from utils.cli_utils import (
    ask_yes_no_question,
    cls,
    edit_obj,
    get_input,
    get_selection,
    print_double_list,
    print_figlet,
    print_single_list,
)
from utils.constants import APP_NAME
from utils.navigation import MenuAction, MenuNavigationCodes, MenuNavigationUserCommands
from utils.photo_processing import (
    IMAGE_TYPE,
    PHOTO_MAX_SIZE,
    THUMBNAIL_MAX_SIZE,
    hash_buffer_md5,
    image_from_bytes,
    rescale_image,
    save_image_to_buffer,
)
from utils.threading import split, THREADS

from threading import Thread

from .base_cli import BaseCLI


class TravelCLI(BaseCLI):
    DESTINATION_PK = f"{Namespaces.TRAVEL}#{TravelEntities.DESTINATION}"
    PLACE_PK = f"{Namespaces.TRAVEL}#{TravelEntities.PLACE}"
    PHOTO_PK = f"{Namespaces.TRAVEL}#{TravelEntities.PHOTO}"
    ALBUM_PK = f"{Namespaces.TRAVEL}#{TravelEntities.ALBUM}"

    DESTINATION_SK_FS = ""
    PLACE_SK_FS = "{destination_id}#{place_id}"
    PHOTO_SK_FS = "{place_id}#{photo_id}"
    ALBUM_SK_FS = "{place_id}#{album_id}"

    def __init__(
        self,
        google_maps_client: GoogleMapsClient,
        immich_client: ImmichClient,
        s3_client: S3Client,
        ddb_client: DDBClient,
    ):
        self.google_maps_client = google_maps_client
        self.immich_client = immich_client
        self.s3_client = s3_client
        self.ddb_client = ddb_client

        self._run = False

        # Set by the batch re-import script so progress does not repaint the
        # screen and destroy the log
        self.quiet = False

        self._menu_actions: List[MenuAction] = [
            MenuAction("Add Destination", self.add_destination),
            MenuAction("Add Place", self.add_place),
            MenuAction("Add Album", self.add_album),
            MenuAction("Add Photos", self.add_photos),
            MenuAction("Edit Destination", self.edit_destination),
            MenuAction("Edit Place", self.edit_place),
            MenuAction("Delete Destination", self.delete_destination),
            MenuAction("Delete Place", self.delete_place),
        ]

    def _print_menu(self) -> None:
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

    def run(self) -> None:
        """
        A method for perfroming a task in the Travel CLI
        """
        self._run = True

        while self._run:
            self._print_menu()
            sel = get_selection(0, len(self._menu_actions), allowed_chars=[])

            if sel == 0:
                self._run = False
                return

            action = self._menu_actions[sel - 1]
            action.command()

    def _get_destinations(self) -> List[Destination]:
        """
        A method for retrieving all Destinations
        """
        query_result = self.ddb_client.get_equals(self.DESTINATION_PK)
        destinations: List[Destination] = [Destination(**obj) for obj in query_result]
        destinations.sort(key=lambda x: [x.country_code, x.name])
        return destinations

    def _get_places(self, destination: Destination) -> List[Place]:
        """
        A method for retrieving all Places for a Destination
        """
        query_result = self.ddb_client.get_begins_with(self.PLACE_PK, destination.place_id)
        places: List[Place] = [Place(**obj) for obj in query_result]
        places.sort(key=lambda x: x.name)
        return places

    def _get_album(self, place: Place) -> Album:
        """
        A method for retrieving the album of a place
        """
        query_result = self.ddb_client.get_begins_with(self.ALBUM_PK, place.place_id)
        if len(query_result) > 1:
            raise InvalidStateException(
                f"More than one album exists for Place: {place.place_id} under Destination: {place.destination_id}"
            )

        if len(query_result) == 0:
            raise InvalidStateException(
                f"No album exists for Place: {place.place_id} under Destination: {place.destination_id}"
            )

        return Album(**query_result[0])

    def add_destination(self) -> None:
        """
        A method for creating a new Destination object
        """
        print_figlet(APP_NAME)

        # Add Destination
        inp = get_input("Enter destination name to use the autocomplete functionality.")
        if inp in [MenuNavigationUserCommands.GO_TO_MAIN_MENU, MenuNavigationUserCommands.GO_BACK]:
            cls()
            return

        suggestions = self.google_maps_client.get_destination_suggestions(inp)
        if suggestions:
            print_figlet(APP_NAME)
            print_single_list([suggestion["description"] for suggestion in suggestions])
            print(f"{len(suggestions) + 1}. Enter Google Place ID Manually")
            print()
            sel = (
                get_selection(
                    0,
                    len(suggestions) + 1,
                    [
                        MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                        MenuNavigationUserCommands.GO_BACK,
                    ],
                )
                - 1
            )

            if sel == MenuNavigationCodes.GO_TO_MAIN_MENU:
                cls()
                return
            elif sel == MenuNavigationCodes.GO_BACK:
                self.add_destination()
                return

        # If Google couldn't find any suggesions or the user doesn't like any of the suggestions generated, then
        # allow the user to manually enter a place id
        if not suggestions or sel == len(suggestions):
            print_figlet(APP_NAME)

            print(
                "Enter in the Place ID below (https://developers.google.com/maps/documentation/javascript/place-id)"
            )
            print()

            id_ = input("Place ID: ")
            if id_ == MenuNavigationUserCommands.GO_TO_MAIN_MENU:
                cls()
                return
            elif id_ == MenuNavigationUserCommands.GO_BACK:
                self.add_destination()
                return

        else:
            id_ = suggestions[sel]["place_id"]

        geocoded_destination: GeocodedDestination = self.google_maps_client.geocode_destination(id_)

        destination = Destination(place_id=id_, **geocoded_destination.asdict())

        # Check if a record for the Destination already exists
        record = self.ddb_client.get_equals(self.DESTINATION_PK, destination.place_id)

        # If a record already exists for the Destination, ensure the user wants to continue
        if record and not ask_yes_no_question(
            f"A record already exists for destination: {destination.place_id}, continue?: "
        ):
            return

        self.edit_destination(destination)

        return

    def add_place(self, destination: Optional[Destination] = None) -> None:
        """
        A method for creating a new Place object
        """
        assert destination is None or isinstance(destination, Destination)

        destinations: List[Destination] = []

        print_figlet(APP_NAME)

        if destination is None:
            destinations = self._get_destinations()
            print_double_list(destinations)
            print()
            sel = get_selection(
                0,
                len(destinations),
                allowed_chars=[
                    MenuNavigationUserCommands.GO_BACK,
                    MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                ],
            )
            if sel in [MenuNavigationCodes.GO_BACK, MenuNavigationCodes.GO_TO_MAIN_MENU]:
                cls()
                return

            print_figlet(APP_NAME)
            destination = destinations[sel - 1]

        print("Selected Destination: {}".format(destination.name))
        print()

        inp = get_input("Enter a place name to use the autocomplete functionality.")

        suggestions = self.google_maps_client.get_place_suggestions(
            inp, location=(float(destination.latitude), float(destination.longitude))
        )

        print()
        print_single_list(
            [
                f"{sug['structured_formatting'].get('main_text', '')} {sug['structured_formatting'].get('secondary_text', '')}"
                for sug in suggestions
            ]
        )
        print()

        sel = get_selection(
            0,
            len(suggestions),
            allowed_chars=[
                MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                MenuNavigationUserCommands.GO_BACK,
            ],
        )
        if sel == MenuNavigationCodes.GO_TO_MAIN_MENU:
            cls()
            return

        elif sel == MenuNavigationCodes.GO_BACK:
            self.add_place(destination=destination)
            return

        # The list displayed to the user starts at 1, so decrement
        selected_place = suggestions[sel - 1]

        data: GeocodedPlace = self.google_maps_client.geocode_place(selected_place["place_id"])

        place = Place(
            **data.asdict(),
            name=selected_place["structured_formatting"]["main_text"],
            destination_id=destination.place_id,
            city=destination.name,
        )

        # Check if a record for the place already exists
        record = self.ddb_client.get_equals(
            self.PLACE_PK,
            self.PLACE_SK_FS.format(destination_id=place.destination_id, place_id=place.place_id),
        )

        # If a record already exists for the Destination, ensure the user wants to continue
        if record and not ask_yes_no_question(
            f"A record already exists for place: {place.place_id}, continue?"
        ):
            return

        self.edit_place(destination, place)

        print_figlet(APP_NAME)
        if ask_yes_no_question("Would you like to add an album to this place? (y/n): "):
            self.add_album(destination=destination, place=place)

        print_figlet(APP_NAME)
        if ask_yes_no_question("Would you like to add another place to this destination? (y/n): "):
            self.add_place(destination=destination)

        return

    def add_album(self, destination=None, place=None) -> None:
        """
        A method for creating a new Album object
        """

        print_figlet(APP_NAME)

        if not destination:
            destinations = self._get_destinations()
            print_double_list(destinations)
            print()
            sel = get_selection(
                1,
                len(destinations),
                allowed_chars=[
                    MenuNavigationUserCommands.GO_BACK,
                    MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                ],
            )
            if sel in [
                MenuNavigationCodes.GO_TO_MAIN_MENU,
                MenuNavigationCodes.GO_BACK,
            ]:
                cls()
                return

            print_figlet(APP_NAME)
            destination = destinations[sel - 1]

        if not place:
            places = self._get_places(destination)
            print_double_list(places)
            print()
            sel = get_selection(
                1,
                len(places),
                allowed_chars=[
                    MenuNavigationUserCommands.GO_BACK,
                    MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                ],
            )
            if sel in [
                MenuNavigationCodes.GO_BACK,
                MenuNavigationCodes.GO_TO_MAIN_MENU,
            ]:
                cls()
                return

            print_figlet(APP_NAME)
            place = places[sel - 1]

        print_figlet(APP_NAME)
        if existing_albums := self._get_existing_albums(place):
            print(f"An Album(s) already exists for this place: {existing_albums}")

        inp = get_input(
            "Enter the album name to use the autocomplete functionality.",
            f"{destination.name} -- {place.name}",
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

        if sel == MenuNavigationCodes.GO_TO_MAIN_MENU:
            cls()
            return

        # Anything else negative is a request to go back, or an entry that
        # cannot be used as an index, so re-prompt rather than crash
        if sel < 0:
            self.add_album(destination, place)
            return

        data = self.immich_client.get_album_info(suggestions[sel - 1][1])

        album = Album(
            album_id=data["id"],
            title=data["albumName"],
            destination_id=destination.place_id,
            place_id=place.place_id,
        )

        # Unlink any album previously attached to this place before writing the
        # new one.  Skip the new album itself, otherwise re-selecting the same
        # album would delete the record just written
        for existing_album in existing_albums:
            if existing_album.album_id != album.album_id:
                self._delete_existing_album(existing_album)

        self.ddb_client.put(
            self.ALBUM_PK,
            self.ALBUM_SK_FS.format(place_id=place.place_id, album_id=album.album_id),
            album.asdict(),
        )

        print_figlet(APP_NAME)
        if ask_yes_no_question("Would you like to add photos to this album? (y/n): "):
            self.add_photos(destination=destination, place=place)

    def _get_existing_albums(self, place: Place) -> List[Album]:
        return [
            Album(**album)
            for album in self.ddb_client.get_begins_with(self.ALBUM_PK, place.place_id)
        ]

    def _delete_existing_album(self, album: Album) -> None:
        self.ddb_client.delete(
            pk=self.ALBUM_PK,
            sk=self.ALBUM_SK_FS.format(place_id=album.place_id, album_id=album.album_id),
        )

    def add_photos(
        self, destination: Optional[Destination] = None, place: Optional[Place] = None
    ) -> None:
        """
        A method for adding photos to a Place
        """

        print_figlet(APP_NAME)

        if destination is None:
            destinations = self._get_destinations()
            print_double_list(destinations)
            print()
            sel = get_selection(
                1,
                len(destinations),
                allowed_chars=[
                    MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                    MenuNavigationUserCommands.GO_BACK,
                ],
            )
            if sel in [
                MenuNavigationCodes.GO_TO_MAIN_MENU,
                MenuNavigationCodes.GO_BACK,
            ]:
                cls()
                return

            print_figlet(APP_NAME)
            destination = destinations[sel - 1]

        print("Selected Destination: {}".format(destination.name))
        print()

        if place is None:
            places = self._get_places(destination)
            print_double_list(places)
            print()

            sel = get_selection(
                1,
                len(places),
                allowed_chars=[
                    MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                    MenuNavigationUserCommands.GO_BACK,
                    MenuNavigationUserCommands.ALL,
                ],
            )
            if sel == MenuNavigationCodes.GO_TO_MAIN_MENU:
                cls()
                return
            elif sel == MenuNavigationCodes.GO_BACK:
                self.add_photos()
                return
            elif sel == MenuNavigationCodes.ALL:
                for place in places:
                    self._process_photos(destination, place)
                return
            else:
                place = places[sel - 1]

        self._process_photos(destination, place)

        print_figlet(APP_NAME)
        if ask_yes_no_question(
            "Would you like to add photos to another place in this destination? (y/n): "
        ):
            self.add_photos(destination=destination)

    def _get_existing_photos(self, place: Place) -> Set[str]:
        existing = self.ddb_client.get_begins_with(self.PHOTO_PK, place.place_id)
        return set([image["hsh"] for image in existing])

    def _process_photos(self, destination: Destination, place: Place) -> None:
        if not self.quiet:
            print_figlet(APP_NAME)
        album = self._get_album(place)
        photos = self.immich_client.get_album_photos(album.album_id)

        existing = self._get_existing_photos(place)
        chunks = split(photos, THREADS)

        progress: Dict[int, float] = {}
        threads = []
        for i, chunk in enumerate(chunks):
            thread = Thread(
                target=self._process_photo, args=(chunk, destination, place, existing, i, progress)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

    def _process_photo(self, chunk, destination, place, existing, thread_no, progress):
        for i, asset in enumerate(chunk):
            img: Image.Image = image_from_bytes(self.immich_client.download_asset(asset["id"]))

            # Hash the rescaled photo before writing anything, so photos that
            # are already recorded are not uploaded to S3 a second time
            rescaled = rescale_image(img, PHOTO_MAX_SIZE)
            buffer = save_image_to_buffer(rescaled)
            hsh = hash_buffer_md5(buffer)

            progress[thread_no] = 100 * ((i + 1) / len(chunk))
            self._print_photo_progress(progress)

            if hsh in existing:
                continue

            photo_src = self._upload_photo_to_s3(buffer, hsh, destination, place)
            thumbnail_src = self._upload_thumbnail_to_s3(img, destination, place)
            photo = Photo(
                photo_id=asset["id"],
                src=photo_src,
                destination_id=destination.place_id,
                place_id=place.place_id,
                height=rescaled.height,
                width=rescaled.width,
                creation_timestamp=self.immich_client.asset_timestamp(asset),
                hsh=hsh,
                thumbnail_src=thumbnail_src,
            )
            self.ddb_client.put(
                self.PHOTO_PK,
                self.PHOTO_SK_FS.format(place_id=place.place_id, photo_id=photo.photo_id),
                photo.asdict(),
            )

    def _print_photo_progress(self, progress):
        if self.quiet:
            return

        print_figlet(APP_NAME)
        print(f"Downloading photos using {THREADS} threads, see progress below...")
        print(" ".join([f"{k}: {v:.2f}%" for k, v in sorted(progress.items())]))

    def _upload_photo_to_s3(
        self, buffer: BytesIO, hsh: str, destination: Destination, place: Place
    ) -> str:
        file_name = f"{hsh}.{IMAGE_TYPE}"
        file_path = self.s3_client.generate_s3_path_for_image(
            destination.place_id, place.place_id, file_name
        )

        return self.s3_client.write_image_to_s3(
            file_path, buffer, ACL="public-read", ContentType=f"image/{IMAGE_TYPE}"
        )

    def _upload_thumbnail_to_s3(
        self, img: Image.Image, destination: Destination, place: Place
    ) -> str:
        img = rescale_image(img, THUMBNAIL_MAX_SIZE)
        buffer = save_image_to_buffer(img)
        hsh = hash_buffer_md5(buffer)
        file_name = f"{hsh}.{IMAGE_TYPE}"
        thumbnail_path = self.s3_client.generate_s3_path_for_thumbnail(
            destination.place_id, place.place_id, file_name
        )
        s3_path = self.s3_client.write_image_to_s3(
            thumbnail_path,
            buffer,
            ACL="public-read",
            ContentType=f"image/{IMAGE_TYPE}",
        )
        return s3_path

    def edit_destination(self, destination: Optional[Destination] = None) -> None:
        """
        A method for editing a Destination
        """
        print_figlet(APP_NAME)
        if destination is None:
            destinations = self._get_destinations()
            print_double_list(destinations)
            print()
            sel = get_selection(
                1,
                len(destinations),
                allowed_chars=[
                    MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                    MenuNavigationUserCommands.GO_BACK,
                ],
            )
            if sel in [
                MenuNavigationCodes.GO_TO_MAIN_MENU,
                MenuNavigationCodes.GO_BACK,
            ]:
                cls()
                return

            print_figlet(APP_NAME)
            destination = destinations[sel - 1]

        new_dest: Destination = edit_obj(destination)
        self.ddb_client.put(self.DESTINATION_PK, destination.place_id, new_dest.asdict())

    # Menu Option 5
    def edit_place(
        self, destination: Optional[Destination] = None, place: Optional[Place] = None
    ) -> None:
        """
        A method for editing a Place
        """
        print_figlet(APP_NAME)
        if not destination:
            destinations = self._get_destinations()
            print_double_list(destinations)
            print()
            sel = get_selection(
                1,
                len(destinations),
                allowed_chars=[
                    MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                    MenuNavigationUserCommands.GO_BACK,
                ],
            )
            if sel in [
                MenuNavigationCodes.GO_TO_MAIN_MENU,
                MenuNavigationCodes.GO_BACK,
            ]:
                cls()
                return

            print_figlet(APP_NAME)
            destination = destinations[sel - 1]

        if place is None:
            places = self._get_places(destination)
            print_double_list(places)
            print()
            sel = get_selection(
                1,
                len(places),
                allowed_chars=[
                    MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                    MenuNavigationUserCommands.GO_BACK,
                ],
            )

            if sel == MenuNavigationCodes.GO_TO_MAIN_MENU:
                cls()
                return

            if sel == MenuNavigationCodes.GO_BACK:
                self.edit_place()
                return

            print_figlet(APP_NAME)
            place = places[sel - 1]

        new_place: Place = edit_obj(place)
        self.ddb_client.put(
            self.PLACE_PK,
            self.PLACE_SK_FS.format(destination_id=place.destination_id, place_id=place.place_id),
            new_place.asdict(),
        )

    def delete_destination(self) -> None:
        """
        A method for deleting a Destination
        """
        print_figlet(APP_NAME)
        destinations = self._get_destinations()
        print_double_list(destinations)
        print()
        sel = get_selection(
            1,
            len(destinations),
            allowed_chars=[
                MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                MenuNavigationUserCommands.GO_BACK,
            ],
        )
        if sel in [
            MenuNavigationCodes.GO_TO_MAIN_MENU,
            MenuNavigationCodes.GO_BACK,
        ]:
            cls()
            return

        print_figlet(APP_NAME)
        destination = destinations[sel - 1]
        self.ddb_client.delete(pk=self.DESTINATION_PK, sk=destination.place_id)

    def delete_place(self) -> None:
        """
        A method for deleting a Place
        """
        print_figlet(APP_NAME)
        destinations = self._get_destinations()
        print_double_list(destinations)
        print()
        sel = get_selection(
            1,
            len(destinations),
            allowed_chars=[
                MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                MenuNavigationUserCommands.GO_BACK,
            ],
        )
        if sel in [
            MenuNavigationCodes.GO_TO_MAIN_MENU,
            MenuNavigationCodes.GO_BACK,
        ]:
            cls()
            return

        destination = destinations[sel - 1]

        print_figlet(APP_NAME)
        places = self._get_places(destination)
        print_double_list(places)
        print()

        sel = get_selection(
            1,
            len(places),
            allowed_chars=[
                MenuNavigationUserCommands.GO_TO_MAIN_MENU,
                MenuNavigationUserCommands.GO_BACK,
            ],
        )
        if sel == MenuNavigationCodes.GO_TO_MAIN_MENU:
            cls()
            return
        if sel == MenuNavigationCodes.GO_BACK:
            self.delete_place()
            return

        place = places[sel - 1]

        self.ddb_client.delete(
            pk=self.PLACE_PK,
            sk=self.PLACE_SK_FS.format(
                destination_id=place.destination_id, place_id=place.place_id
            ),
        )

        return
