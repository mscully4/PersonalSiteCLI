import uuid
from typing import Any, Dict

from attr import fields_dict

from clients import DDBClient, Namespaces, ResumeEntities, S3Client
from models.resume import Education, Job, Skill
from utils.cli_utils import cls, get_input, get_selection, print_figlet
from utils.constants import APP_NAME
from utils.photo_processing import (IMAGE_TYPE, download_image,
                                    hash_buffer_md5, save_image_to_buffer)

from .base_cli import BaseCLI


class ResumeCLI(BaseCLI):
    JOB_PK = f"{Namespaces.RESUME}#{ResumeEntities.JOB}"
    EDUCATION_PK = f"{Namespaces.RESUME}#{ResumeEntities.EDUCATION}"
    SKILL_PK = f"{Namespaces.RESUME}#{ResumeEntities.SKILL}"

    def __init__(
        self,
        s3_client: S3Client,
        ddb_client: DDBClient,
    ):
        self.s3_client = s3_client
        self.ddb_client = ddb_client

        self._run = False
        self._commands = [self.add_education, self.add_job, self.add_skill]

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

    def _download_image(self, prompt: str):
        img = download_image(get_input(prompt))
        buffer = save_image_to_buffer(img)
        hsh = hash_buffer_md5(buffer)
        file_name = f"{hsh}.{IMAGE_TYPE}"
        file_path = f"resume/images/{file_name}"

        s3_path = self.s3_client.write_image_to_s3(
            file_path, buffer, ACL="public-read", ContentType="image/png"
        )
        return s3_path

    def add_job(self):
        data = {}
        for field in Job.__annotations__:
            pretty_field = field.replace("_", " ").title()
            if field == "id":
                data[field] = str(uuid.uuid4())
                continue

            elif field == "logo_url":
                data[field] = self._download_image(pretty_field)
            else:
                data[field] = get_input(pretty_field)

        job = Job(**data)
        self.ddb_client.put(self.JOB_PK, job.id, job.asdict())

    def add_education(self):
        print_figlet(APP_NAME)

        data: Dict[str, Any] = {}
        for field in Education.__annotations__:
            pretty_field = field.replace("_", " ").title()
            if field == "id":
                data[field] = str(uuid.uuid4())
                continue
            elif field == "logo_url":
                data[field] = self._download_image(pretty_field)
            else:
                data[field] = get_input(pretty_field)

        edu = Education(**data)
        self.ddb_client.put(self.EDUCATION_PK, edu.id, edu.asdict())

    def add_skill(self):
        print_figlet(APP_NAME)

        data = {}
        for field in fields_dict(Skill):
            pretty_field = field.replace("_", " ").title()
            if field == "id":
                data[field] = str(uuid.uuid4())
                continue

            elif field == "logo_url":
                data[field] = self._download_image(pretty_field)
            else:
                data[field] = get_input(pretty_field)

        skill = Skill(**data)
        self.ddb_client.put(self.SKILL_PK, skill.id, skill.asdict())
