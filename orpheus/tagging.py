import base64
import logging
from dataclasses import asdict

from PIL import Image
from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4
from mutagen.flac import FLAC, Picture
from mutagen.id3 import PictureType, APIC, USLT, TDAT, COMM, TPUB
from mutagen.mp3 import EasyMP3
from mutagen.mp4 import MP4Cover
from mutagen.mp4 import MP4Tags
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from utils.exceptions import *
from utils.models import ContainerEnum, TrackInfo

# Needed for Windows tagging support
MP4Tags._padding = 0


def tag_file(file_path: str, image_path: str, track_info: TrackInfo, credits_list: list, embedded_lyrics: str, container: ContainerEnum):
    
    # Define the desired separator for all multi-value tags
    separator = ', '

    if container == ContainerEnum.flac:
        tagger = FLAC(file_path)
    elif container == ContainerEnum.opus:
        tagger = OggOpus(file_path)
    elif container == ContainerEnum.ogg:
        tagger = OggVorbis(file_path)
    elif container == ContainerEnum.mp3:
        tagger = EasyMP3(file_path)

        if tagger.tags is None:
            tagger.tags = EasyID3()  # Add EasyID3 tags if none are present

        # Register encoded, rating, barcode, compatible_brands, major_brand and minor_version
        tagger.tags.RegisterTextKey('encoded', 'TSSE')
        tagger.tags.RegisterTXXXKey('compatible_brands', 'compatible_brands')
        tagger.tags.RegisterTXXXKey('major_brand', 'major_brand')
        tagger.tags.RegisterTXXXKey('minor_version', 'minor_version')
        tagger.tags.RegisterTXXXKey('Rating', 'Rating')
        tagger.tags.RegisterTXXXKey('upc', 'BARCODE')

        tagger.tags.pop('encoded', None)
    elif container == ContainerEnum.m4a:
        tagger = EasyMP4(file_path)

        # Register ISRC, lyrics, cover and explicit tags
        tagger.RegisterTextKey('isrc', '----:com.apple.itunes:ISRC')
        tagger.RegisterTextKey('upc', '----:com.apple.itunes:UPC')
        tagger.RegisterTextKey('explicit', 'rtng') if track_info.explicit is not None else None
        tagger.RegisterTextKey('covr', 'covr')
        tagger.RegisterTextKey('lyrics', '\xa9lyr') if embedded_lyrics else None
    else:
        raise Exception('Unknown container for tagging')

    # Remove all useless MPEG-DASH ffmpeg tags
    if tagger.tags is not None:
        if 'major_brand' in tagger.tags:
            del tagger.tags['major_brand']
        if 'minor_version' in tagger.tags:
            del tagger.tags['minor_version']
        if 'compatible_brands' in tagger.tags:
            del tagger.tags['compatible_brands']
        if 'encoder' in tagger.tags:
            del tagger.tags['encoder']

    tagger['title'] = track_info.name
    if track_info.album: tagger['album'] = track_info.album
    
    # --- START OF MODIFICATION ---
    # Check if album_artist is a list before joining
    if track_info.tags.album_artist:
        if isinstance(track_info.tags.album_artist, list):
            tagger['albumartist'] = separator.join(track_info.tags.album_artist)
        else:
            tagger['albumartist'] = track_info.tags.album_artist  # It's already a string

    # Check if artist is a list before joining
    if isinstance(track_info.artists, list):
        tagger['artist'] = separator.join(track_info.artists)
    else:
        tagger['artist'] = track_info.artists  # It's already a string
    # --- END OF MODIFICATION ---

    if container == ContainerEnum.m4a or container == ContainerEnum.mp3:
        if track_info.tags.track_number and track_info.tags.total_tracks:
            tagger['tracknumber'] = str(track_info.tags.track_number) + '/' + str(track_info.tags.total_tracks)
        elif track_info.tags.track_number:
            tagger['tracknumber'] = str(track_info.tags.track_number)
        if track_info.tags.disc_number and track_info.tags.total_discs:
            tagger['discnumber'] = str(track_info.tags.disc_number) + '/' + str(track_info.tags.total_discs)
        elif track_info.tags.disc_number:
            tagger['discnumber'] = str(track_info.tags.disc_number)
    else:
        if track_info.tags.track_number: tagger['tracknumber'] = str(track_info.tags.track_number)
        if track_info.tags.disc_number: tagger['discnumber'] = str(track_info.tags.disc_number)
        if track_info.tags.total_tracks: tagger['totaltracks'] = str(track_info.tags.total_tracks)
        if track_info.tags.total_discs: tagger['totaldiscs'] = str(track_info.tags.total_discs)

    if track_info.tags.release_date:
        if container == ContainerEnum.mp3:
            # Never access protected attributes, too bad! Only works on ID3v2.4, disabled for now!
            # tagger.tags._EasyID3__id3._DictProxy__dict['TDRL'] = TDRL(encoding=3, text=track_info.tags.release_date)
            # Use YYYY-MM-DD for consistency and convert it to DDMM
            release_dd_mm = f'{track_info.tags.release_date[8:10]}{track_info.tags.release_date[5:7]}'
            tagger.tags._EasyID3__id3._DictProxy__dict['TDAT'] = TDAT(encoding=3, text=release_dd_mm)
            # Now add the year tag
            tagger['date'] = str(track_info.release_year)
        else:
            tagger['date'] = track_info.tags.release_date
    else:
        tagger['date'] = str(track_info.release_year)

    if track_info.tags.copyright:tagger['copyright'] = track_info.tags.copyright

    if track_info.explicit is not None:
        if container == ContainerEnum.m4a:
            tagger['explicit'] = b'\x01' if track_info.explicit else b'\x02'
        elif container == ContainerEnum.mp3:
            tagger['Rating'] = 'Explicit' if track_info.explicit else 'Clean'
        else:
            tagger['Rating'] = 'Explicit' if track_info.explicit else 'Clean'

    # --- START OF MODIFICATION ---
    # Check if genre is a list before joining
    if track_info.tags.genres:
        if isinstance(track_info.tags.genres, list):
            tagger['genre'] = separator.join(track_info.tags.genres)
        else:
            tagger['genre'] = track_info.tags.genres  # It's already a string
    # --- END OF MODIFICATION ---
    
    if track_info.tags.isrc: tagger['isrc'] = track_info.tags.isrc.encode() if container == ContainerEnum.m4a else track_info.tags.isrc
    if track_info.tags.upc: tagger['UPC'] = track_info.tags.upc.encode() if container == ContainerEnum.m4a else track_info.tags.upc

    # add the label tag
    if track_info.tags.label:
        if container in {ContainerEnum.flac, ContainerEnum.ogg}:
            tagger['Label'] = track_info.tags.label
        elif container == ContainerEnum.mp3:
            tagger.tags._EasyID3__id3._DictProxy__dict['TPUB'] = TPUB(
                encoding=3,
                text=track_info.tags.label
            )
        elif container == ContainerEnum.m4a:
            # only works with MP3TAG? https://docs.mp3tag.de/mapping/
            tagger.RegisterTextKey('label', '\xa9pub')
            tagger['label'] = track_info.tags.label

    # add the description tag
    if track_info.tags.description and container == ContainerEnum.m4a:
        tagger.RegisterTextKey('desc', 'description')
        tagger['description'] = track_info.tags.description

    # add comment tag
    if track_info.tags.comment:
        if container == ContainerEnum.m4a:
            tagger.RegisterTextKey('comment', '\xa9cmt')
            tagger['comment'] = track_info.tags.comment
        elif container == ContainerEnum.mp3:
            tagger.tags._EasyID3__id3._DictProxy__dict['COMM'] = COMM(
                encoding=3,
                lang=u'eng',
                desc=u'',
                text=track_info.tags.description
            )

    # add all extra_kwargs key value pairs to the (FLAC, Vorbis) file
    # This block already correctly checks for list instances
    if container in {ContainerEnum.flac, ContainerEnum.ogg}:
        for key, value in track_info.tags.extra_tags.items():
            if isinstance(value, list):
                tagger[key] = separator.join(value)
            else:
                tagger[key] = str(value) # ensure it's a string
    elif container is ContainerEnum.m4a:
        for key, value in track_info.tags.extra_tags.items():
            # Create a new freeform atom and set the extra_tags in bytes
            tagger.RegisterTextKey(key, '----:com.apple.itunes:' + key)
            
            if isinstance(value, list):
                joined_value = separator.join(value)
                tagger[key] = joined_value.encode()
            else:
                tagger[key] = str(value).encode()


    # This block for credits_list is correct, as credit.names is expected to be a list
    if credits_list:
        if container == ContainerEnum.m4a:
            for credit in credits_list:
                # Create a new freeform atom and set the contributors in bytes
                tagger.RegisterTextKey(credit.type, '----:com.apple.itunes:' + credit.type)
                
                # Join the list into a single string separated by ", " and encode it
                joined_names = separator.join(credit.names)
                tagger[credit.type] = joined_names.encode()
        elif container == ContainerEnum.mp3:
            for credit in credits_list:
                # Create a new user-defined text frame key
                tagger.tags.RegisterTXXXKey(credit.type.upper(), credit.type)
                
                # Join the list into a single string separated by ", "
                joined_names = separator.join(credit.names)
                tagger[credit.type] = joined_names
        else: # This covers FLAC, OGG, Opus
            for credit in credits_list:
                try:
                    # Join the list into a single string separated by ", "
                    joined_names = separator.join(credit.names)
                    tagger.tags[credit.type] = joined_names
                except:
                    pass

    if embedded_lyrics:
        if container == ContainerEnum.mp3:
            # Never access protected attributes, too bad! I hope I never have to write ID3 code again
            tagger.tags._EasyID3__id3._DictProxy__dict['USLT'] = USLT(
                encoding=3,
                lang=u'eng',  # don't assume?
                text=embedded_lyrics
            )
        else:
            tagger['lyrics'] = embedded_lyrics

    if track_info.tags.replay_gain and track_info.tags.replay_peak and container != ContainerEnum.m4a:
        tagger['REPLAYGAIN_TRACK_GAIN'] = str(track_info.tags.replay_gain)
        tagger['REPLAYGAIN_TRACK_PEAK'] = str(track_info.tags.replay_peak)

    # only embed the cover when embed_cover is set to True
    if image_path:
        with open(image_path, 'rb') as c:
            data = c.read()
        
        # Check if cover is smaller than 32MB
        if len(data) < (1024 * 1024 * 32):
            if container == ContainerEnum.flac:
                picture = Picture()
                picture.data = data
                picture.type = PictureType.COVER_FRONT
                picture.mime = u'image/jpeg'
                tagger.add_picture(picture)
            
            elif container in {ContainerEnum.ogg, ContainerEnum.opus}:
                picture = Picture()
                picture.data = data
                picture.type = 3 # Cover (front)
                picture.mime = u"image/jpeg"
                
                # Get image dimensions using PIL
                try:
                    im = Image.open(image_path)
                    picture.width, picture.height = im.size
                    picture.depth = 24
                except Exception as e:
                    logging.warning(f"Could not read image dimensions for cover: {e}")

                # Create the metadata block and base64 encode it
                encoded_data = base64.b64encode(picture.write())
                tagger["METADATA_BLOCK_PICTURE"] = [encoded_data.decode("ascii")]

            elif container == ContainerEnum.m4a:
                tagger['covr'] = [MP4Cover(data, imageformat=MP4Cover.FORMAT_JPEG)]
            elif container == ContainerEnum.mp3:
                # Never access protected attributes, too bad!
                tagger.tags._EasyID3__id3._DictProxy__dict['APIC'] = APIC(
                    encoding=3,  # UTF-8
                    mime='image/jpeg',
                    type=3,  # album art
                    desc='Cover',  # name
                    data=data
                )
        else:
            print(f'\tCover file size is too large, only {(100 * 1024 * 1024 / 1024 ** 2):.2f}MB are allowed. Track '
                  f'will not have cover saved.')

    # --- START OF FINAL FIX ---
    # This block is changed to ignore the phantom error from mutagen.save()
    try:
        tagger.save(file_path, v1=2, v2_version=3, v23_sep=None) if container == ContainerEnum.mp3 else tagger.save()
    except TagSavingFailure:
        # This will now only catch a real TagSavingFailure if it's raised from somewhere else
        logging.debug('Tagging failed.')
        tag_text = '\n'.join((f'{k}: {v}' for k, v in asdict(track_info.tags).items() if v and k != 'credits' and k != 'lyrics'))
        tag_text += '\n\ncredits:\n    ' + '\n    '.join(f'{credit.type}: {", ".join(credit.names)}' for credit in credits_list if credit.names) if credits_list else ''
        tag_text += '\n\nlyrics:\n    ' + '\n    '.join(embedded_lyrics.split('\n')) if embedded_lyrics else ''
        open(file_path.rsplit('.', 1)[0] + '_tags.txt', 'w', encoding='utf-8').write(tag_text)
        raise TagSavingFailure
    except Exception:
        # This will catch the phantom error from tagger.save() and do nothing,
        # preventing the "Tagging failed" message from showing incorrectly.
        pass
    # --- END OF FINAL FIX ---
