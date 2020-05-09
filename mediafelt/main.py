"""
Mediafelt TV and movie file parse and move using guessit library
"""
import argparse
import collections
import glob
import json
import logging
import logging.config
import os
import re
import sys

import guessit
import yaml

from mediafelt import videxts

LOG = logging.getLogger(__name__)


def main():
    """
    Entry point
    """
    parser = argparse.ArgumentParser(
        description="Parse and move media files",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        'source', type=str, help='Source directory/file')
    parser.add_argument(
        'destination', type=str, help='Root destination directory')
    parser.add_argument(
        '--tv-dir', type=str,
        help="Directory relative to destination to place TV shows",
        default="Series")
    parser.add_argument(
        '--movie-dir', type=str,
        help="Directory relative to destination to place movies",
        default="Movies")
    parser.add_argument(
        '--dry-run', action="store_true", help="Don't actually move anything")
    args = parser.parse_args()

    parser.add_argument(
        'destination', type=str, help='Root destination directory')

    LOG.info("Parsing with arguments: %s", str(args))

    if os.path.isdir(args.source):
        file_paths = _glob_files(args.source)
    else:
        file_paths = [args.source]

    # log.debug(file_paths)
    _execute(
        file_paths, args.destination, args.movie_dir, args.tv_dir,
        args.dry_run)


def _glob_files(prefix):
    """
    Recursively glob files, filtered by long list of video file extensions

    :param prefix: directory to scan from
    :return: sorted list of video file paths
    """
    return sorted(
        file_path for file_path
        in glob.glob(os.path.join(glob.escape(prefix), "**"), recursive=True)
        if videxts.ext_regexp.search(file_path) is not None
    )


def _execute(file_paths, destination, movie_dir, tv_dir, dry_run):
    """
    Parse and move (unless a dry run) a given list of files

    :param file_paths: list of input files relative to working directory
    :param destination: root of destination to move files
    :param movie_dir: path relative to destination to move movies
    :param tv_dir: path relative to destination to move TV episodes
    :param dry_run: don't actually move any files
    """
    file_infos = _parse_files(file_paths)
    episodes = file_infos.get("episode")
    movies = file_infos.get("movie")

    if episodes is not None:
        path_mapping = _get_episode_paths(episodes)
        path_prefix = os.path.abspath(os.path.join(destination, tv_dir))
        path_mapping = _get_dest_paths(path_prefix, path_mapping)
        _move_files(path_mapping, dry_run)

    if movies is not None:
        _clean_multi_file_movies(movies)
        path_mapping = _get_movie_paths(movies)
        path_prefix = os.path.abspath(os.path.join(destination, movie_dir))
        path_mapping = _get_dest_paths(path_prefix, path_mapping)
        _move_files(path_mapping, dry_run)


def _parse_files(file_paths):
    """
    Parse list of file paths using guessit

    :param file_paths: list of file paths
    :return: list of file infos by title by type (movie or episode)
    """
    # log.debug("Found: %s", file_paths)
    file_infos = collections.defaultdict(lambda: collections.defaultdict(list))
    # Parse file names.
    for file_path in file_paths:
        file_info = guessit.guessit(file_path)
        file_name = os.path.split(file_path)[-1]
        if file_name != file_path:
            file_info_file = guessit.guessit(file_name)
            file_info.update(file_info_file)
        file_info["file_path"] = file_path
        title = file_info.get("series", file_info.get("title"))
        title = title.title()
        file_infos[file_info.get("type")][title].append(file_info)

    # Add year to title if available.
    for _media_type, file_info_list_by_title in file_infos.items():
        title_map = []
        for title, file_info_list in file_info_list_by_title.items():
            years = tuple(filter(None, (
                _FileInfo(file_info).year for file_info in file_info_list)))
            if years and all(year == years[0] for year in years):
                title_map.append((title, "%s %s" % (title, years[0])))

        for old_title, new_title in title_map:
            file_info_list_by_title[new_title] = file_info_list_by_title.pop(
                old_title)

    return file_infos


def _clean_multi_file_movies(movies):
    """
    Disambiguate movie files with the same title

    :param movies: guessit info dicts by title
    """
    multi_file = (
        _FileInfoList(movie_info_list)
        for movie_info_list in movies.values() if len(movie_info_list) > 1)

    for file_list in multi_file:
        if file_list.all_contain("part"):
            LOG.debug("Multi-part movie: %s", file_list.dumps())
            continue

        if file_list.all_contain_non_equal("year"):
            LOG.debug(
                "Same title different year movies: %s", file_list.dumps())
            continue

        if file_list.all_contain_non_equal("screen_size"):
            file_list_sorted = file_list.sort(
                lambda file_info: int(
                    re.sub('[^0-9]', '', file_info["screen_size"])))
        else:
            file_list_sorted = file_list.sort(
                lambda file_info: os.path.getsize(file_info["file_path"]))

        largest_file = file_list_sorted[-1]
        LOG.info(
            "Choosing %s from %s", largest_file["file_path"],
            file_list.dumps())
        file_list.reset(largest_file)


def _get_episode_paths(file_infos_by_title):
    """
    Construct destination path for TV episodes

    :param file_infos_by_title: guessit info dicts by title
    :return: tuples mapping input file path to output file path
    """
    file_path_mapping = []

    for title, file_infos in file_infos_by_title.items():
        for file_info in file_infos:
            file_info = _FileInfo(file_info)

            file_name_parts = filter(None, (
                title,
                file_info.episode,
                file_info.part,
                file_info.episode_title,
                file_info.screen_size,
                file_info.video_profile,
                file_info.audio_codec,
                file_info.audio_channels,
            ))
            file_path_mapping.append(
                file_info.path_mapping(title, file_name_parts))

    return file_path_mapping


def _get_movie_paths(file_infos_by_title):
    """
    Construct destination path for movies

    :param file_infos_by_title: guessit info dicts by title
    :return: tuples mapping input file path to output file path
    """
    file_path_mapping = []

    for title, file_infos in file_infos_by_title.items():
        for file_info in file_infos:
            file_info = _FileInfo(file_info)

            file_name_parts = filter(None, (
                title,
                file_info.part,
                file_info.screen_size,
                file_info.video_profile,
                file_info.audio_codec,
                file_info.audio_channels,
            ))
            file_path_mapping.append(
                file_info.path_mapping(title, file_name_parts))

    return file_path_mapping


def _get_dest_paths(prefix, sub_path_mapping):
    """
    Join destination paths in mapping with prefix

    :param prefix: prefix to add
    :param sub_path_mapping: mapping of input paths to destination child paths
    :return: new path mapping with prefix applied to destination
    """
    path_mapping = []
    for old_path, new_sub_path in sub_path_mapping:
        path_mapping.append((old_path, os.path.join(prefix, new_sub_path)))
    return path_mapping


def _move_files(path_mapping, dry_run):
    """
    Move files on file system from input paths to output paths

    :param path_mapping: list of tuples of input and output file paths
    :param dry_run: if truthy, don't actuall move, just log
    """
    for old_path, new_path in path_mapping:
        LOG.info("%s -> %s", old_path, new_path)
        if not dry_run:
            os.renames(old_path, new_path)


class _FileInfo:
    """
    Wrapper around guessit file info to construct strings
    """
    def __init__(self, file_info):
        self.__file_info = file_info

    def path_mapping(self, title, file_name_parts):
        """
        Construct destination path from title and list of descriptor strings

        :param title: title of movie/episode
        :param file_name_parts: list of strings containing info to add to file
        name
        :return: tuple of source path and destination file path
        """
        file_name = ".".join(file_name_parts)
        file_path_from = self.__file_info["file_path"]
        _, file_ext = os.path.splitext(file_path_from)
        file_path_to = "%s%s" % (
            os.path.join(title, file_name), file_ext)
        file_path_to = file_path_to.replace(" ", ".")
        return file_path_from, file_path_to

    @property
    def episode(self):
        """
        Construct episode string
        
        :return: season+episode(s) or date
        """
        season = self.__season
        episode = self.__file_info.get(
            "episode_list", self.__file_info.get("episode"))
        if isinstance(episode, list):
            episode = "-".join("%s%02d" % (season, ep) for ep in episode)
        elif episode is not None:
            episode = "%sE%02d" % (season, episode)
        else:
            episode = self.__file_info.get("date")
            if episode is not None:
                episode = episode.strftime("%Y-%m-%d")
        return episode

    @property
    def year(self):
        """
        Get year string in round brackets, if available

        :return: year string or None
        """
        year = self.__file_info.get("year")
        if year is not None:
            year = "(%d)" % year
        return year

    @property
    def part(self):
        """
        Get file/movie/episode part number prefixed with "Part"

        :return: part string
        """
        part = self.__file_info.get("part")
        if part is not None:
            part = "Part %d" % part
        return part

    @property
    def audio_codec(self):
        """
        Get abbreviated audio codec string

        :return: audio codec string
        """
        audio_codec = self.__file_info.get("audio_codec")
        if audio_codec is not None:
            audio_codec = audio_codec.replace(
                "Dolby Digital Plus", "DDP").replace("Dolby Digital", "DD")
        return audio_codec

    @property
    def screen_size(self):
        """
        Get screen size, falling back on source (e.g. HDTV) if unavailable

        :return: screen size string
        """
        return self.__file_info.get(
            "screen_size", self.__file_info.get("source"))

    @property
    def __season(self):
        """
        Construct season+episode string

        :return: season+episode string
        """
        season = self.__file_info.get("season", "")
        if season:
            season = "S%02d" % season
        return season

    @property
    def video_profile(self):
        """
        Get abbreviated video profile

        :return: video profile string
        """
        video_profile = self.__file_info.get("video_profile")
        if video_profile is not None:
            video_profile = video_profile.replace(
                "High Efficiency Video Coding", "HEVC")
        return video_profile

    def __getattr__(self, prop):
        """
        Proxy to underlying guessit info for other properties

        :param prop: property to fetch
        :return: string of property
        """
        return self.__file_info.get(prop)


class _FileInfoList:
    """
    Utility functions for a list of guessit file infos
    """
    def __init__(self, file_list):
        self.__file_list = file_list

    def all_contain_non_equal(self, prop):
        """
        Check if all info dicts contain a property, and they are not all equal

        :param prop: property to check
        :return: True if all info dicts have property and they are not equal
        """
        if self.all_contain(prop):
            if not self.__all_equal(prop):
                return True
        return False

    def __all_equal(self, prop):
        """
        Check if given property is equal in all info dicts

        :param prop: property to check
        :return: True if `prop` is equal in all info dicts
        """
        return all(
            file_info[prop] == self.__file_list[0][prop]
            for file_info in self.__file_list)

    def all_contain(self, prop):
        """
        Check if all info dicts contain a given property

        :param prop: property to check
        :return: True if all info dicts contain `prop`
        """
        return all(file_info.get(prop) for file_info in self.__file_list)

    def sort(self, key):
        """
        Return the input info dict list sorted using given key

        :param key: key to sort by
        :return: sorted list of file info dicts
        """
        return sorted(self.__file_list, key=key)

    def reset(self, item):
        """
        Reset list of file info dicts to a single element list of given item

        :param item: item to replace with
        """
        self.__file_list.clear()
        self.__file_list.append(item)

    def dumps(self):
        """
        Dump list of file info dicts to a string

        :return: JSON formatted string
        """
        return _dumps(self.__file_list)


def _dumps(file_infos):
    """
    Dump a list of guessit file info dicts to a JSON string

    :param file_infos: list of guessit dicts
    :return: JSON string
    """
    return json.dumps(file_infos, indent=2, default=str)


def _setup_logging():
    """
    Read logging YAML config and set up catch-all logging for exceptions
    """
    directory = os.path.dirname(os.path.realpath(__file__))

    with open(os.path.join(directory, "logging.yaml")) as file:
        config = yaml.safe_load(file.read())
    logging.config.dictConfig(config)

    sys.excepthook = _exc_hook


def _exc_hook(exc_type, value, tb):
    """
    Exception hook to log exceptions

    :param exc_type: type of exception
    :param value: exception object
    :param tb: traceback object
    """
    LOG.exception("Uncaught exception", exc_info=(exc_type, value, tb))


_setup_logging()
