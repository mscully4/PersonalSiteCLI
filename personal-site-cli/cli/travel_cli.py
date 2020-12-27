from utils.cli_utils import (
    print_figlet,
    clr_line,
    cls,
    get_selection,
    get_input,
    print_single_list,
    print_double_list,
    edit_obj,
    ask_yes_no_question,
)
from utils.constants import APP_NAME
from models.travel import Destination, Place, Album, Photo
from clients import (
    ddb_client,
    Namespaces,
    TravelEntities,
    s3_client,
    google_maps_client,
    google_photos_client,
)
from typing import List
from utils.photo_processing import (
    download,
    hash_buffer_md5,
    rescale_image,
    save_image_to_buffer,
    COVER_PHOTO_MAX_SIZE,
    PHOTO_MAX_SIZE,
    IMAGE_TYPE,
)
from .base_cli import BaseCLI


class TravelCLI(BaseCLI):
    DESTINATION_PK = f"{Namespaces.TRAVEL}#{TravelEntities.DESTINATION}"
    PLACE_PK = f"{Namespaces.TRAVEL}#{TravelEntities.PLACE}"
    PHOTO_PK = f"{Namespaces.TRAVEL}#{TravelEntities.PHOTO}"
    ALBUM_PK = f"{Namespaces.TRAVEL}#{TravelEntities.ALBUM}"

    def __init__(
        self,
        google_maps_client: google_maps_client,
        google_photos_client: google_photos_client,
        s3_client: s3_client,
        ddb_client: ddb_client,
    ):
        self.google_maps_client = google_maps_client
        self.google_photos_client = google_photos_client
        self.s3_client = s3_client
        self.ddb_client = ddb_client

        self._run = False
        self._commands = [
            self.add_destination,
            self.add_place,
            self.add_album,
            self.add_photos,
            self.edit_destination,
            self.edit_place,
            self.delete_destination,
            self.delete_place,
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
        for i, command in enumerate(self._commands):
            pretty_name = command.__name__.replace("_", " ").title()
            print(f"{i+1}. {pretty_name}")

        print()

    async def run(self):
        """
        A method for perfroming a task in the Travel CLI
        """
        self._run = True

        while self._run:
            self._print_menu()
            sel = get_selection(1, len(self._commands), allowed_chars="")

            if sel == 0:
                self._run = False
                return

            self._commands[sel - 1]()

    def _get_destinations(self) -> List[Destination]:
        """
        A method for retrieving all Destinations

        Returns:
            destinations: A list of Destination objects
        """
        query_result = self.ddb_client.get_equals(self.DESTINATION_PK)
        destinations: List[Destination] = [Destination(**obj) for obj in query_result]
        return destinations

    def _get_places(self, destination: Destination) -> List[Place]:
        """
        A method for retrieving all Places for a Destination

        Arguments:
            destination (Destination): The Destination to retrieve places for

        Returns:
            places: A list of Place objects
        """
        query_result = self.ddb_client.get_begins_with(
            self.PLACE_PK, destination.place_id
        )
        places: List[Place] = [Place(**obj) for obj in query_result]
        return places

    def _get_album(self, place: Place) -> Album:
        """
        A method for retrieving the album of a place

        Arguments:
            place (Place): The Place to retrieve albums for

        Returns:
            albums: An Album object
        """
        query_result = self.ddb_client.get_begins_with(self.ALBUM_PK, place.place_id)
        assert len(query_result) == 1, "Was expecting only one Album"
        return Album(**query_result[0])

    def add_destination(self):
        """
        A method for creating a new Destination object
        """
        print_figlet(APP_NAME)

        # Add Destination
        inp = get_input("Enter destination name to use the autocomplete functionality.")
        if inp in ["/", "<"]:
            cls()
            return

        suggestions = self.google_maps_client.get_destination_suggestions(inp)
        if suggestions:
            print_figlet(APP_NAME)
            print_single_list([suggestion["description"] for suggestion in suggestions])
            print(f"{len(suggestions) + 1}. Enter Google Place ID Manually")
            print()
            sel = get_selection(0, len(suggestions) + 1) - 1

            if sel == "/":
                cls()
                return
            elif sel == "<":
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
            if id_ == "/":
                cls()
                return
            elif id_ == "<":
                self.add_destination()
                return

        else:
            id_ = suggestions[sel]["place_id"]

        data = self.google_maps_client.geocode_destination(id_)
        # Set type to "" to allow user to change in edit call
        destination = Destination(**data, type="")

        # Check if a record for the Destination already exists
        record = self.ddb_client.get_equals(self.DESTINATION_PK, destination.place_id)

        # If a record already exists, don't add it again
        if len(record) == 0:
            self.edit_destination(destination)

        return

    async def add_place(self, destination: Destination = None):
        """
        A method for creating a new Place object

        Arguments:
            destination (Destination): The Destination to add the Place to.  If None, user is prompted to select Destination
        """
        assert destination == None or isinstance(destination, Destination)

        print_figlet(APP_NAME)

        # Add Place to Destinations
        if not destination:
            destinations = self._get_destinations()
            print_double_list(destinations)
            print()
            sel = get_selection(1, len(destinations), allowed_chars="/<")
            if sel == "/" or sel == "<":
                cls()
                return

            print_figlet(APP_NAME)
            destination = destinations[sel - 1]

        print("Selected Destination: {}".format(destination.name))
        print()

        inp = get_input("Enter a place name to use the autocomplete functionality.")

        suggestions = self.google_maps_client.get_place_suggestions(
            inp, location=[destination.latitude, destination.longitude]
        )

        print()
        print_single_list(
            [
                f"{sug['structured_formatting'].get('main_text', '')} {sug['structured_formatting'].get('secondary_text', '')}"
                for sug in suggestions
            ]
        )
        print()
        sel = get_selection(0, len(destinations), allowed_chars="/<")
        if sel == "/":
            cls()
            return

        elif sel == "<":
            self.add_place(destination=destination)
            return

        # The list displayed to the user starts at 1, so decrement
        selected_place = suggestions[sel - 1]

        data = self.google_maps_client.geocode_place(selected_place["place_id"])

        place = Place(
            **data,
            name=suggestions[sel]["structured_formatting"]["main_text"],
            destination_id=destination.place_id,
            city=destination.name,
        )

        # Check if a record for the place already exists
        record = self.ddb_client.get_equals(
            f"{Namespaces.TRAVEL}#{TravelEntities.PLACE}", place.place_id
        )

        # If a record already exists, don't add it again
        if len(record) == 0:
            self.edit_place(destination, place)

        print_figlet(APP_NAME)
        if ask_yes_no_question("Would you like to add an album to this place? (y/n): "):
            await self.add_album(destination=destination, place=place)

        print_figlet(APP_NAME)
        if ask_yes_no_question(
            "Would you like to add another place to this destination? (y/n): "
        ):
            await self.add_place(destination=destination)

        return

    async def add_album(self, destination=None, place=None):
        """
        A method for creating a new Album object

        Arguments:
            destination (Destination): The Destination the Album will fall under.  If None, user is prompted to select Destination
            place (Place): The Place to add the Album to.  If None, user is prompted to select Destination.
        """

        print_figlet(APP_NAME)

        if not destination:
            destinations = self._get_destinations()
            print_double_list(destinations)
            print()
            sel = get_selection(1, len(destinations), allowed_chars="/<")
            if sel == "/" or sel == "<":
                cls()
                return

            print_figlet(APP_NAME)
            destination = destinations[sel - 1]

        if not place:
            places = self._get_places(destination)
            print_double_list(places)
            print()
            sel = get_selection(1, len(places), allowed_chars="/<")
            if sel == "/" or sel == "<":
                cls()
                return

            print_figlet(APP_NAME)
            place = places[sel - 1]

        print_figlet(APP_NAME)
        inp = get_input(
            "Enter the album name to use the autocomplete functionality.",
            f"{destination.name} -- {place.name}",
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
        sel = get_selection(0, len(suggestions)) - 1

        data = self.google_photos_client.get_album_info(suggestions[sel][1])

        # Download the cover photo and store it in S3
        download_url = data["coverPhotoBaseUrl"]
        img = download(download_url)
        img = rescale_image(img, COVER_PHOTO_MAX_SIZE)
        buffer = save_image_to_buffer(img)
        hsh = hash_buffer_md5(buffer)
        file_name = f"{hsh}.{IMAGE_TYPE}"
        file_path = self.s3_client.generate_s3_path_for_image(
            destination.place_id, place.place_id, file_name
        )
        s3_path = self.s3_client.write_image_to_s3(
            file_path, buffer, ACL="public-read", ContentType="image/png"
        )

        album = Album(
            album_id=data["id"],
            title=data["title"],
            cover_photo_id=data["coverPhotoMediaItemId"],
            cover_photo_url=s3_path,
            destination_id=destination.place_id,
            place_id=place.place_id,
        )

        sk: str = f"{place.place_id}#{album.album_id}"
        self.ddb_client.put(self.ALBUM_PK, sk, album.asdict())

        self._upload_cover_photo(album)

        print_figlet(APP_NAME)
        if ask_yes_no_question("Would you like to add photos to this album? (y/n): "):
            self.add_photos(destination=destination, place=place)

    def _upload_cover_photo(self, album: Album):
        """
        A method for downloading an album cover photo, uploading it to S3 and inserting to DDB

        Arguments:
            album (Album): The Album the cover photo is being added to
        """
        cover_photo = Photo(
            photo_id=album.cover_photo_id,
            place_id=album.place_id,
            destination_id=album.destination_id,
            is_cover_image=True,
        )
        cover_photo.download(url=album.cover_photo_download_url)
        album.cover_photo_src = cover_photo.write(self.s3)
        self.albums_table.insert(album)

    def add_photos(self, destination: Destination = None, place: Place = None):
        """
        Menu Option 4

        A method for adding photos to a Place

        Arguments:
            destination (Destination): The Destination to add photos to.  If None, user is prompted to select one.
            place (Place): The Place to add photos to.  If None, user is prompted to select one.
        """

        print_figlet(APP_NAME)
        destinations = self._get_destinations()
        print_double_list(destinations)
        print()
        sel = get_selection(1, len(destinations), allowed_chars="/<")
        if sel == "/" or sel == "<":
            cls()
            return

        print_figlet(APP_NAME)
        destination = destinations[sel - 1]

        places = self._get_places(destination)
        print_double_list(places)
        print()

        if sel == "/":
            cls()
            return

        sel = get_selection(1, len(places), allowed_chars="/<")
        if sel == "<":
            self.add_photos()
            return

        place = places[sel - 1]

        print_figlet(APP_NAME)
        self._upload_photos(destination, place)

    def _upload_photos(self, destination: Destination, place: Place):
        """
        A method for downloading photos, uploading them to S3 and inserting to DDB

        Arguments:
            destination (Destination): The Destination of the Place photos will be added to. If None, the user will select one
            place (Place): The Place the photos belong to. If None, the user will select one
        """
        album = self._get_album(place)
        photos = self.google_photos_client.get_album_photos(album.album_id)

        for i, obj in enumerate(photos):
            print(f"Uploading Photo: {i + 1} out of {len(photos)}")
            img = download(obj["baseUrl"])
            rescale_image(img, PHOTO_MAX_SIZE)
            buffer = save_image_to_buffer(img)
            hsh = hash_buffer_md5(buffer)
            file_name = f"{hsh}.{IMAGE_TYPE}"
            file_path = self.s3_client.generate_s3_path_for_image(
                destination.place_id, place.place_id, file_name
            )

            s3_path = self.s3_client.write_image_to_s3(
                file_path, buffer, ACL="public-read", ContentType="image/png"
            )
            photo = Photo(
                photo_id=obj["id"],
                src=s3_path,
                destination_id=destination.place_id,
                place_id=place.place_id,
                height=img.height,
                width=img.width,
                creation_timestamp=obj["mediaMetadata"]["creationTime"],
                is_cover_image=False,
            )
            sk: str = place.place_id + "#" + photo.photo_id
            self.ddb_client.put(self.PHOTO_PK, sk, photo.asdict())
            clr_line()

    def edit_destination(self, destination: Destination = None):
        """
        A method for editing a Destination

        Arguments:
            destination (Destination): The Destination to edit
        """
        print_figlet(APP_NAME)
        if not destination:
            destinations = self._get_destinations()
            print_double_list(destinations)
            print()
            sel = get_selection(1, len(destinations), allowed_chars="/<")
            if sel == "/" or sel == "<":
                cls()
                return

            print_figlet(APP_NAME)
            destination = destinations[sel - 1]

        destination = edit_obj(destination)
        self.ddb_client.put(
            self.DESTINATION_PK, destination.place_id, destination.asdict()
        )

    # Menu Option 5
    def edit_place(self, destination: Destination = None, place: Place = None):
        """
        A method for editing a Place

        Arguments:
            destination (Destination): The Destination the Place belongs to. If None, the user will be prompted to select one
            place (Place): The Place to edit. If None, the user will be prompted to select one
        """
        print_figlet(APP_NAME)
        if not destination:
            destinations = self._get_destinations()
            print_double_list(destinations)
            print()
            sel = get_selection(1, len(destinations), allowed_chars="/<")
            if sel == "/" or sel == "<":
                cls()
                return

            print_figlet(APP_NAME)
            destination = destinations[sel - 1]

        if not place:
            places = self._get_places(destination)
            print_double_list(places)
            print()
            sel = get_selection(1, len(places), allowed_chars="/<")
            if sel == "/":
                cls()
                return

            if sel == "<":
                self.edit_place()
                return

            print_figlet(APP_NAME)
            place = places[sel - 1]

        place = edit_obj(place)
        sk: str = place.destination_id + "#" + place.place_id
        self.ddb_client.put(self.PLACE_PK, sk, place.asdict())

    def delete_destination(self):
        """
        A method for deleting a Destination
        """
        print_figlet(APP_NAME)
        destinations = self._get_destinations()
        print_double_list(destinations)
        print()
        sel = get_selection(1, len(destinations), allowed_chars="/<")
        if sel == "/" or sel == "<":
            cls()
            return

        print_figlet(APP_NAME)
        destination = destinations[sel - 1]
        self.ddb_client.delete(pk=self.DESTINATION_PK, sk=destination.place_id)

    def delete_place(self):
        """
        A method for deleting a Place
        """
        print_figlet(APP_NAME)
        destinations = self._get_destinations()
        print_double_list(destinations)
        print()
        sel = get_selection(1, len(destinations), allowed_chars="/<")
        if sel == "/" or sel == "<":
            cls()
            return

        destination = destinations[sel - 1]

        print_figlet(APP_NAME)
        places = self._get_places(destination)
        print_double_list(places)
        print()

        if sel == "/":
            cls()
            return

        sel = get_selection(1, len(places), allowed_chars="/<")
        if sel == "<":
            self.delete_place()
            return

        place = places[sel - 1]

        sk: str = f"{place.destination_id}#{place.place_id}"
        self.ddb_client.delete(pk=self.PLACE_PK, sk=sk)

        return
