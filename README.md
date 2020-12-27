# Personal Site CLI

This is a CLI that I use to add data to my personal website!

My site can be found at michaeljscully.com

## About This Project

This project is written predominately in Python. It provides an interface for me to add more data to personal site. My site is broken up into different views, this CLI follows a similar pattern. There is a base CLI that allows the user to specify which view to add data to, then the user depending on the user's selection, they are routed to the appropriate sub CLI.

## About the Stack

As previously mentioned, this project is written almost entirely in Python. Data entered is written to a DynamoDB table, which my personal site reads from. Images and files are stored in S3. Many different APIs and services are used to ease the burden of data entry. The Google Maps API is eased to autocomplete place names and geocode places. The Google Photos API is used to retrieve Photos from the user's Google account.

## Views

There is a sub-CLI for every view that my website has.

My website currently has the following views:

1. Home
2. Travel
3. Resume
