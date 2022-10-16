from typing import Tuple, List

import googlemaps as gm
from models.google_maps import GeocodedDestination, GeocodedPlace


class GoogleMapsClient(object):
    CITIES_TYPE = "(cities)"
    DEFAULT_SEARCH_RADIUS_METERS = 25000

    def __init__(self, api_key: str):
        self._gm: gm.Client = gm.Client(key=api_key)

    def get_destination_suggestions(self, text: str) -> List:
        """
        A method for autocompleting city names given a text entry
        """
        return self._gm.places_autocomplete(text, types=[self.CITIES_TYPE])

    def get_place_suggestions(
        self,
        text: str,
        location: Tuple[float, float] = None,
        radius: int = DEFAULT_SEARCH_RADIUS_METERS,
    ) -> List:
        """
        A method for autocompleting places given a text entry
        """
        return self._gm.places_autocomplete(text, location=location, radius=radius)

    def geocode_destination(self, place_id: str) -> GeocodedDestination:
        """
        A method for retrieving information about a city given its place_id
        """
        geo_data = self._gm.reverse_geocode(place_id)[0]

        country, country_code = "", ""
        for comp in geo_data["address_components"]:
            if "country" in comp["types"]:
                country = comp["long_name"]
                country_code = comp["short_name"]

        return GeocodedDestination(
            name=geo_data["address_components"][0]["long_name"],
            country=country,
            country_code=country_code,
            latitude=geo_data["geometry"]["location"]["lat"],
            longitude=geo_data["geometry"]["location"]["lat"],
        )

    def geocode_place(self, place_id: str) -> GeocodedPlace:
        """
        A method for retrieving information about a place given its place_id
        """
        geo_data = self._gm.reverse_geocode(place_id)[0]

        country, zip_code, street, street_number, state = [""] * 5
        for comp in geo_data["address_components"]:
            if "country" in comp["types"]:
                country = comp["long_name"]
            if "postal_code" in comp["types"]:
                zip_code = comp["long_name"]
            if "street_number" in comp["types"]:
                street_number = comp["long_name"]
            if "route" in comp["types"]:
                street = comp["long_name"]
            if "administrative_area_level_1" in comp["types"]:
                state = comp["long_name"]

        return GeocodedPlace(
            place_id=geo_data["place_id"],
            address=street + " " + street_number,
            state=state,
            country=country,
            zip_code=zip_code,
            latitude=geo_data["geometry"]["location"]["lat"],
            longitude=geo_data["geometry"]["location"]["lng"],
        )
