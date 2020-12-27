from .base_cli import BaseCLI
from .travel_cli import TravelCLI
from utils.constants import APP_NAME
from utils.cli_utils import print_figlet, cls, get_selection
from clients import google_maps_client, google_photos_client, s3_client, ddb_client


class PersonalSiteCLI(BaseCLI):
    def __init__(
        self,
        google_maps_client: google_maps_client,
        google_photos_client: google_photos_client,
        s3_client: s3_client,
        ddb_client: ddb_client,
    ):
        self.gp = google_photos_client
        self.gm = google_maps_client
        self.s3 = s3_client
        self.dynamo = ddb_client

        self._menu_options = ["Travel", "Resume"]
        self._travel_cli = TravelCLI(
            google_maps_client, google_photos_client, s3_client, ddb_client
        )

        self._run = False

    def _print_menu(self):
        cls()

        print_figlet(APP_NAME)
        print("Main Menu")

        print("0. To Exit")
        for i, o in enumerate(self._menu_options):
            print(f"{i+1}. {o}")

        print()

    async def run(self):
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
                pass
