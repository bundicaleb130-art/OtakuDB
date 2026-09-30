import time
import requests
import psycopg2

API_URL = "https://graphql.anilist.co"

PAGE_SIZE = 50
MAX_PAGES = 10


def get_media(page, media_type):
    query = """
    query ($page: Int, $perPage: Int, $type: MediaType) {
        Page(page: $page, perPage: $perPage) {
            pageInfo {
                hasNextPage
            }
            media(type: $type, sort: ID) {
                id
                title {
                    romaji
                    english
                }
                format
                status
                startDate {
                    year
                }
                averageScore
            }
        }
    }
    """

    variables = {
        "page": page,
        "perPage": PAGE_SIZE,
        "type": media_type
    }

    for attempt in range(3):
        try:
            response = requests.post(
                API_URL,
                json={
                    "query": query,
                    "variables": variables
                },
                timeout=60
            )

            response.raise_for_status()

            result = response.json()

            if "errors" in result:
                raise RuntimeError(result["errors"])

            return result["data"]["Page"]

        except requests.RequestException as error:
            print(f"Request failed (attempt {attempt + 1}/3): {error}")

            if attempt < 2:
                time.sleep(5)

    raise RuntimeError("API request failed after 3 attempts")


def connect_database():
    password = input("Enter PostgreSQL password: ")

    return psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        database="otaku_db",
        user="postgres",
        password=password
    )


def import_media(media_list, media_type, connection):
    cursor = connection.cursor()

    inserted = 0
    skipped = 0

    for media in media_list:
        title_data = media.get("title") or {}

        title = (
            title_data.get("english")
            or title_data.get("romaji")
        )

        if not title:
            continue

        status = media.get("status")
        year = (media.get("startDate") or {}).get("year")
        rating = media.get("averageScore")
        media_format = media.get("format")

        cursor.execute(
            """
            INSERT INTO titles
                (title, media_type, format, status, release_year, rating)
            VALUES
                (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (title) DO NOTHING
            """,
            (
                title[:100],
                media_type,
                media_format or "UNKNOWN",
                status,
                year,
                rating / 10 if rating else None
            )
        )

        if cursor.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    connection.commit()
    cursor.close()

    return inserted, skipped


def main():
    print("=" * 50)
    print("OtakuDB Bulk Importer")
    print("=" * 50)

    connection = connect_database()

    total_inserted = 0
    total_skipped = 0

    for media_type in ["ANIME", "MANGA"]:

        print()
        print(f"Importing {media_type}...")

        for page in range(1, MAX_PAGES + 1):

            print(f"Page {page}/{MAX_PAGES}...", end=" ")

            try:
                page_data = get_media(page, media_type)
                media_list = page_data["media"]

                if media_type == "ANIME":
                    database_type = "Anime"
                else:
                    database_type = "Manhwa"

                inserted, skipped = import_media(
                    media_list,
                    database_type,
                    connection
                )

                total_inserted += inserted
                total_skipped += skipped

                print(
                    f"received {len(media_list)}, "
                    f"inserted {inserted}, "
                    f"skipped {skipped}"
                )

                if not page_data["pageInfo"]["hasNextPage"]:
                    break

                time.sleep(1)

            except Exception as error:
                print(f"\nError: {error}")
                break

    connection.close()

    print()
    print("=" * 50)
    print("IMPORT COMPLETE")
    print("=" * 50)
    print(f"Inserted: {total_inserted}")
    print(f"Skipped duplicates: {total_skipped}")


if __name__ == "__main__":
    main()
