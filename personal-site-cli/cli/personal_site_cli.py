from clients import DDBClient, GoogleMapsClient, GooglePhotosClient, S3Client
from utils.cli_utils import cls, get_selection, print_figlet
from utils.constants import APP_NAME

from .base_cli import BaseCLI
from .resume_cli import ResumeCLI
from .travel_cli import TravelCLI


class PersonalSiteCLI(BaseCLI):
    def __init__(
        self,
        google_maps_client: GoogleMapsClient,
        google_photos_client: GooglePhotosClient,
        s3_client: S3Client,
        ddb_client: DDBClient,
    ):
        self.gp = google_photos_client
        self.gm = google_maps_client
        self.s3 = s3_client
        self.dynamo = ddb_client

        self._menu_options = ["Travel", "Resume"]
        self._travel_cli = TravelCLI(
            google_maps_client, google_photos_client, s3_client, ddb_client
        )
        self._resume_cli = ResumeCLI(s3_client, ddb_client)

        self._run = False

    def _print_menu(self) -> None:
        cls()

        print_figlet(APP_NAME)
        print("Main Menu")

        print("0. To Exit")
        for i, o in enumerate(self._menu_options):
            print(f"{i+1}. {o}")

        print()

    async def run(self) -> None:
        """
        The method running the CLI application.  The user can select menu prompts to perform different tasks
        """

        self._run = True

        while self._run:
            self._print_menu()
            sel = get_selection(0, len(self._menu_options))

            if sel == 0:
                self._run = False
                if not self.gp.done:
                    self.gp.albums.cancel()
            elif sel == 1:
                await self._travel_cli.run()
            elif sel == 2:
                await self._resume_cli.run()
