# mediafelt
Parse movie and TV show file names in one directory (e.g. downloads), then
rename and move the files to a Kodi-compatible directory structure.

Will only move files, not delete them.  It is left as a manual step to
move/remove any leftover files/directories (e.g. subtitles, screenshots).

Structure is similar to 
`<title>.(<year>)/<title>.(<year>).S<season>E<episode>.<episode name>.<video resolution>.<audio codec>.<audio channels>.ext`

```
usage: mediafelt [-h] [--tv-dir TV_DIR] [--movie-dir MOVIE_DIR] [--dry-run]
                 source destination

Parse and move media files

positional arguments:
  source                Source directory/file
  destination           Root destination directory

optional arguments:
  -h, --help            show this help message and exit
  --tv-dir TV_DIR       Directory relative to destination to place TV shows
  --movie-dir MOVIE_DIR
                        Directory relative to destination to place movies
  --dry-run             Don't actually move anything
```
