import argparse
import collections
import glob
import json
import logging
import logging.config
import os
import re

import guessit
import yaml

from mediafelt import videxts

log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Parse and move media files')
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

    with open("/tmp/mediafelt.log", "w+") as f:
        f.write(str(args) + "\n")

    if os.path.isdir(args.source):
        file_paths = glob_files(args.source)
    else:
        file_paths = [args.source]

    # log.debug(file_paths)
    execute(
        file_paths, args.destination, args.movie_dir, args.tv_dir,
        args.dry_run)


def execute(file_paths, destination, movie_dir, tv_dir, dry_run):
    file_infos = parse_files(file_paths)
    episodes = file_infos.get("episode")
    movies = file_infos.get("movie")

    if episodes is not None:
        path_mapping = get_episode_paths(episodes)
        path_prefix = os.path.abspath(os.path.join(destination, tv_dir))
        path_mapping = get_dest_paths(path_prefix, path_mapping)
        move_files(path_mapping, dry_run)

    if movies is not None:
        clean_multi_file_movies(movies)
        path_mapping = get_movie_paths(movies)
        path_prefix = os.path.abspath(os.path.join(destination, movie_dir))
        path_mapping = get_dest_paths(path_prefix, path_mapping)
        move_files(path_mapping, dry_run)


def parse_files(file_paths):
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
    for media_type, file_info_list_by_title in file_infos.items():
        title_map = []
        for title, file_info_list in file_info_list_by_title.items():
            years = tuple(filter(None, (
                FileInfo(file_info).year for file_info in file_info_list)))
            if years and all(year == years[0] for year in years):
                title_map.append((title, "%s %s" % (title, years[0])))

        for old_title, new_title in title_map:
            file_info_list_by_title[new_title] = file_info_list_by_title.pop(
                old_title)

    return file_infos


def clean_multi_file_movies(movies):
    multi_file = (
        FileInfoList(movie_info_list)
        for movie_info_list in movies.values() if len(movie_info_list) > 1)

    for file_list in multi_file:
        if file_list.all_contain("part"):
            log.debug("Multi-part movie: %s", file_list.dumps())
            continue

        if file_list.all_contain_non_equal("year"):
            log.debug(
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
        log.debug(
            "Choosing %s from %s", largest_file["file_path"],
            file_list.dumps())
        file_list.reset(largest_file)


def get_episode_paths(file_infos_by_title):
    file_path_mapping = []

    for title, file_infos in file_infos_by_title.items():
        for file_info in file_infos:
            file_info = FileInfo(file_info)

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


def get_movie_paths(file_infos_by_title):
    file_path_mapping = []

    for title, file_infos in file_infos_by_title.items():
        for file_info in file_infos:
            file_info = FileInfo(file_info)

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


def get_dest_paths(prefix, sub_path_mapping):
    path_mapping = []
    for old_path, new_sub_path in sub_path_mapping:
        path_mapping.append((old_path, os.path.join(prefix, new_sub_path)))
    return path_mapping


def move_files(path_mapping, dry_run):
    for old_path, new_path in path_mapping:
        log.info("%s -> %s", old_path, new_path)
        if not dry_run:
            os.renames(old_path, new_path)


class FileInfo(object):
    def __init__(self, file_info):
        self.__file_info = file_info

    def path_mapping(self, title, file_name_parts):
        file_name = ".".join(file_name_parts)
        file_path_from = self.__file_info["file_path"]
        _, file_ext = os.path.splitext(file_path_from)
        file_path_to = "%s%s" % (
            os.path.join(title, file_name), file_ext)
        file_path_to = file_path_to.replace(" ", ".")
        return (file_path_from, file_path_to)

    @property
    def episode(self):
        season = self.__season
        episode = self.__file_info.get(
            "episode_list", self.__file_info.get("episode"))
        if isinstance(episode, list):
            episode = "-".join("%s%02d" % (season, ep) for ep in episode)
        elif episode is not None:
            episode = "%sE%02d" % (season, episode)
        return episode

    @property
    def year(self):
        year = self.__file_info.get("year")
        if year is not None:
            year = "(%d)" % year
        return year

    @property
    def part(self):
        part = self.__file_info.get("part")
        if part is not None:
            part = "Part %d" % part
        return part

    @property
    def audio_codec(self):
        audio_codec = self.__file_info.get("audio_codec")
        if audio_codec is not None:
            audio_codec = audio_codec.replace(
                "Dolby Digital Plus", "DDP").replace(
                "Dolby Digital", "DD")
        return audio_codec

    @property
    def screen_size(self):
        return self.__file_info.get(
            "screen_size", self.__file_info.get("source"))

    @property
    def __season(self):
        season = self.__file_info.get("season", "")
        if season:
            season = "S%02d" % season
        return season

    @property
    def video_profile(self):
        video_profile = self.__file_info.get("video_profile")
        if video_profile is not None:
            video_profile = video_profile.replace(
                "High Efficiency Video Coding", "HEVC")
        return video_profile

    def __getattr__(self, property):
        return self.__file_info.get(property)


class FileInfoList(object):
    def __init__(self, file_list):
        self.__file_list = file_list

    def all_contain_non_equal(self, property):
        if self.all_contain(property):
            if not self.__all_equal(property):
                return True
        return False

    def __all_equal(self, property):
        return all(
            file_info[property] == self.__file_list[0][property]
            for file_info in self.__file_list)

    def all_contain(self, property):
        return all(file_info.get(property) for file_info in self.__file_list)

    def sort(self, key):
        return sorted(self.__file_list, key=key)

    def reset(self, item):
        self.__file_list.clear()
        self.__file_list.append(item)

    def dumps(self):
        return dumps(self.__file_list)


def dumps(file_infos):
   return json.dumps(file_infos, indent=2, default=str)


def glob_files(prefix):
    return sorted(
        file_path for file_path
        in glob.glob(os.path.join(glob.escape(prefix), "**"), recursive=True)
        if videxts.ext_regexp.search(file_path) is not None
    )


def setup_logging():
    directory = os.path.dirname(os.path.realpath(__file__))

    with open(os.path.join(directory, "logging.yaml")) as f:
        config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)

setup_logging()
