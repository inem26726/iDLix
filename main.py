import sys
from src.idlixHelper import IdlixHelper, logger
import inquirer

DOWNLOAD_ACTIONS = {
    "Download Movie by URL": "Movie",
    "Download Episode Series by URL": "Series episode",
}


def clear_screen():
    """Clear the terminal without spawning a shell.

    The original code called os.system("cls"/"clear"), which forks a shell on
    every menu redraw. ANSI CSI sequences do the same job in-process and are
    understood by every terminal this CLI realistically runs in.
    """
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="", flush=True)


def print_header():
    print("\n")
    print("  _ ____  _     _      ")
    print(" (_)  _ \\| |   (_)_  __")
    print(" | | | | | |   | \\\\ \\/ /")
    print(" | | |_| | |___| |>  < ")
    print(" |_|____/|_____|_/_/\\\\_\\\\")
    print("                       ")
    print("Idlix movie, series, and subtitle downloader")
    print("https://github.com/inem26726/iDLix")
    print("")


def ask_menu():
    """Render the main menu.

    inquirer.prompt() returns None when the user hits Ctrl+C (its default is
    raise_keyboard_interrupt=False), so every caller must handle a None answer
    instead of subscripting it. Any other renderer/terminal failure is turned
    into the same None so a broken TTY never dumps a traceback.
    """
    question = [
        inquirer.List(
            "action",
            message="Select action",
            choices=[
                "Download Movie by URL",
                "Download Episode Series by URL",
                "Download subtitle only by URL",
                "Exit",
            ],
            carousel=True,
        )
    ]
    try:
        return inquirer.prompt(question)
    except KeyboardInterrupt:
        return None
    except Exception as error_prompt:
        logger.error("Menu could not be rendered: {}".format(error_prompt))
        return None


def select_variant(idlix_helper, variant_playlist):
    """Ask which stream variant to download.

    Returns True only when a variant was actually selected, so a Ctrl+C here
    skips the download instead of crashing on answer['variant'].
    """
    question = [
        inquirer.List(
            "variant",
            message="Select variant",
            choices=[
                str(item.get("id")) + "." + str(item.get("resolution"))
                for item in variant_playlist
            ],
            carousel=True,
        )
    ]
    answer = inquirer.prompt(question)
    if not answer:
        logger.warning("Variant selection cancelled, download skipped")
        return False

    for variant in variant_playlist:
        if variant["id"] == answer["variant"].split(".")[0]:
            logger.success("Selected variant : " + variant["resolution"])
            idlix_helper.set_m3u8_url(variant["uri"])
            return True

    logger.warning("Selected variant not found, download skipped")
    return False


def resolve_variant_or_skip(idlix_helper, get_m3u8_url):
    """Handle the variant-playlist branch shared by movie and series flows.

    Returns True when the helper is ready to download.
    """
    if get_m3u8_url["is_variant_playlist"]:
        logger.warning("This video has variant playlist")
        return select_variant(idlix_helper, get_m3u8_url["variant_playlist"])

    logger.warning("This video has no variant playlist")
    return True


def run_download(idlix_helper, video_data, label):
    """Download the m3u8 stream plus its subtitle, logging every outcome."""
    logger.info("[INFO] Starting downloading " + video_data["video_name"] + "...")
    download_m3u8 = idlix_helper.download_m3u8()
    if download_m3u8["status"]:
        logger.success(
            "[SUCCESS] {} {} downloaded".format(label, video_data["video_name"])
        )
        download_subtitle = idlix_helper.get_subtitle()
        if download_subtitle["status"]:
            logger.success("Download subtitle success")
        else:
            logger.error("Error download subtitle")
    else:
        logger.error("Error downloading m3u8")


def run_stream_flow(idlix_helper, url, video_data, label, not_found):
    """Shared body for the movie and series menu entries.

    `not_found` keeps the original per-flow wording ("movie" vs "series").
    """
    if not video_data["status"]:
        logger.error("Couldn't find the " + not_found)
        return

    get_embed_url = idlix_helper.get_embed_url()
    if not get_embed_url["status"]:
        logger.error("Error getting embed url")
        return

    get_m3u8_url = idlix_helper.get_m3u8_url()
    if not get_m3u8_url["status"]:
        logger.error("Error getting m3u8 url")
        return

    if not resolve_variant_or_skip(idlix_helper, get_m3u8_url):
        return

    run_download(idlix_helper, video_data, label)


def run_subtitle_flow(idlix_helper, url):
    """Download only the subtitle for a movie or episode URL."""
    if url.startswith(idlix_helper.BASE_WEB_URL + "movie/"):
        video_data = idlix_helper.get_movie_data(url)
    else:
        video_data = idlix_helper.get_series_data(url)

    if not video_data["status"]:
        logger.error("[FAILED] Couldn't find the subtitle")
        return

    get_embed_url = idlix_helper.get_embed_url()
    if not get_embed_url["status"]:
        logger.error("[ERROR] Failed embeded url: " + get_embed_url["message"])
        return

    get_m3u8_url = idlix_helper.get_m3u8_url()
    if not get_m3u8_url["status"]:
        logger.error("[ERROR] Failed get get_m3u8_url: " + get_m3u8_url["message"])
        return

    download_subtitle = idlix_helper.get_subtitle()
    if download_subtitle["status"]:
        logger.success("Download subtitle success")
    else:
        logger.error("Error download subtitle: " + download_subtitle["message"])


def main():
    # readchar drives the menu through termios on stdin; with stdin redirected
    # (main.py < file, a pipe, CI) it raises termios.error(25, 'Inappropriate
    # ioctl for device') and dumps a traceback. Bail out with a real message.
    if not sys.stdin.isatty():
        print(
            "iDLix needs an interactive terminal, but stdin is not a TTY.",
            file=sys.stderr,
        )
        return 1

    status_exit = False
    # Ctrl+C / Ctrl+D anywhere below must end the program cleanly rather than
    # dump a traceback: inquirer swallows its own Ctrl+C (returning None) but
    # input() still raises KeyboardInterrupt / EOFError.
    try:
        while not status_exit:
            clear_screen()
            print_header()

            idlix_helper = IdlixHelper()

            answer = ask_menu()
            if not answer:
                logger.info("Exiting")
                break

            if answer["action"] == "Download Movie by URL":
                url = input(
                    "Enter movie URL (Ex: "
                    + idlix_helper.BASE_WEB_URL
                    + "movie/kung-fu-panda-4-2024/): \n"
                )
                run_stream_flow(
                    idlix_helper,
                    url,
                    idlix_helper.get_movie_data(url),
                    "Movie",
                    "movie",
                )

            #
            # Download episode in series
            #
            elif answer["action"] == "Download Episode Series by URL":
                url = input(
                    "Enter series episode URL (Ex: "
                    + idlix_helper.BASE_WEB_URL
                    + "episode/squid-game-season-2-episode-2/): \n"
                )
                run_stream_flow(
                    idlix_helper,
                    url,
                    idlix_helper.get_series_data(url),
                    "Series episode",
                    "series",
                )

            elif answer["action"] == "Download subtitle only by URL":
                url = input(
                    "Enter movie/episode URL (Ex: "
                    + idlix_helper.BASE_WEB_URL
                    + "episode/squid-game-season-2-episode-2/): \n"
                )
                run_subtitle_flow(idlix_helper, url)

            else:
                logger.info("Exiting")
                status_exit = True

            if not status_exit:
                input("\n\nPress Enter to continue...")
    except (KeyboardInterrupt, EOFError):
        logger.info("\nInterrupted, exiting.")
        status_exit = True


if __name__ == "__main__":
    sys.exit(main())
