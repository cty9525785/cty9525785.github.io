# Tianyu Chen's website

Source for a personal academic website: a home page that lists the papers, and a page with its movies for each paper written as first or co-first author.

## Build

The pages are generated from `content/site.toml` and `content/papers.toml`:

    python -X utf8 tools/build.py

The generated HTML is committed, so the site is served as plain static files with no build step on the host.

The movies, posters and home page tiles in `media/` are made with ffmpeg; the drawn tiles also need numpy and Pillow:

    python -X utf8 tools/media.py --ffmpeg path/to/ffmpeg --src folder [--src folder ...]

A clip tile is cut from a paper's movies by its ffmpeg graph in `tools/tiles/`; a drawn tile comes from `tools/drawings.py`.

Run the tests with (numpy and Pillow are needed; FFMPEG lets the tile timing test decode frames):

    FFMPEG=path/to/ffmpeg python -X utf8 -m unittest discover -s tests -t . -v

## Credits

- Home page layout adapted from Jon Barron's website: https://github.com/jonbarron/jonbarron.github.io
- Paper pages adapted from the Academic Project Page Template, licensed under CC BY-SA 4.0: https://github.com/eliahuhorwitz/Academic-project-page-template
- Lato font by Lukasz Dziedzic (tyPoland), from Google Fonts, licensed under the SIL Open Font License 1.1: `assets/fonts/lato/OFL.txt`
- Movies and figures are from the papers credited under each one.
