"""Tools for using Encapsulated PostScript."""

__version__ = '$Revision: 1.5 $'

import os
import sys

from . import utils


#  Exception which should not propagate outside printing support.
class EPSError(Exception):
    pass


class EPSImage:
    __xscale = 1.0
    __yscale = 1.0

    def __init__(self, data, bbox):
        self.data = data
        self.bbox = bbox
        ll_x, ll_y, ur_x, ur_y = bbox
        self.__width = utils.distance(ll_x, ur_x)
        self.__height = utils.distance(ll_y, ur_y)

    def reset(self):
        self.__xscale = self.__yscale = 1.0

    def restrict(self, width=None, height=None):
        w, h = self.get_size()          # current size
        rf = 1.0                        # reduction factor
        if width and width < w:
            rf = width / w
        if height and height < h:
            rf = min(rf, height / h)
        self.__yscale = self.__yscale * rf
        self.__xscale = self.__xscale * rf

    def get_scale(self):
        return self.__xscale, self.__yscale

    def get_size(self):
        return (self.__width * self.__xscale), \
               (self.__height * self.__yscale)

    def set_size(self, width, height):
        self.__xscale = width / self.__width
        self.__yscale = height / self.__height

    def set_width(self, width):
        aspect = self.__yscale / self.__xscale
        self.__xscale = width / self.__width
        self.__yscale = self.__xscale * aspect

    def set_height(self, height):
        aspect = self.__xscale / self.__yscale
        self.__yscale = height / self.__height
        self.__xscale = self.__yscale * aspect


#  Dictionary of image converters from key ==> EPS.
#  The values need to be formatted against the keyword arguments
#  `i' for the input filename and `o' for the output filename.
image_converters = {
    ('gif', 'color') : 'giftopnm {i} | pnmtops -noturn >{o}',
    ('gif', 'grey') : 'giftopnm {i} | ppmtopgm | pnmtops -noturn >{o}',
    ('jpeg', 'color') : 'djpeg -pnm {i} | pnmtops -noturn >{o}',
    ('jpeg', 'grey') : 'djpeg -grayscale -pnm {i} | pnmtops -noturn >{o}',
    ('pbm', 'grey') : 'pbmtoepsi {i} >{o}',
    ('pgm', 'grey') : 'pnmtops -noturn {i} >{o}',
    ('ppm', 'color') : 'pnmtops -noturn {i} >{o}',
    ('ppm', 'grey') : 'ppmtopgm {i} | pnmtops -noturn >{o}',
    ('rast', 'color') : 'rasttopnm {i} | pnmtops -noturn >{o}',
    ('rast', 'grey') : 'rasttopnm {i} | ppmtopgm | pnmtops -noturn >{o}',
    ('rgb', 'color') : 'rgb3toppm {i} | pnmtops -noturn >{o}',
    ('rgb', 'grey') : 'rgb3toppm {i} | ppmtopgm | pnmtops -noturn >{o}',
    ('tiff', 'color') : 'tifftopnm {i} | pnmtops -noturn >{o}',
    ('tiff', 'grey') : 'tifftopnm {i} | ppmtopgm | pnmtops -noturn >{o}',
    ('xbm', 'grey') : 'xbmtopbm {i} | pbmtoepsi >{o}',
    ('xpm', 'color') : 'xpmtoppm {i} | pnmtops -noturn >{o}',
    ('xpm', 'grey') : 'xpmtoppm {i} | ppmtopgm | pnmtops -noturn >{o}'
    }


def load_image_file(img_fn, greyscale):
    """Generate EPS and the bounding box for an image stored in a file.

    This function attempts to use the Python Imaging Library if it is
    installed, otherwise it uses a fallback approach using external
    conversion programs.
    """
    import tempfile
    eps_fn = tempfile.mktemp()
    try:
        load_image_pil(img_fn, greyscale, eps_fn)
    except (AttributeError, IOError, ImportError):
        # AttributeError is possible with partial installation of PIL,
        # and IOError can mean a recognition failure.
        load_image_internal(img_fn, greyscale, eps_fn)
    img = load_eps(eps_fn)              # img is (data, bbox)
    os.unlink(eps_fn)
    return img


def load_image_internal(img_fn, greyscale, eps_fn):
    """Use external converters to generate EPS."""
    from imghdr import what
    imgtype = what(img_fn)
    if not imgtype:
        os.unlink(img_fn)
        raise EPSError('Could not identify image type.')
    cnv_key = (imgtype, 'grey' if greyscale else 'color')
    if cnv_key not in image_converters:
        cnv_key = (imgtype, 'grey')
    if cnv_key not in image_converters:
        os.unlink(img_fn)
        raise EPSError('No converter defined for {} images.'.format(imgtype))
    img_command = image_converters[cnv_key]
    img_command = img_command.format(i=img_fn, o=eps_fn)
    try:
        if os.system(img_command + ' 2>/dev/null'):
            os.unlink(img_fn)
            if os.path.exists(eps_fn):
                os.unlink(eps_fn)
            raise EPSError('Error converting image to EPS.')
    except:
        if os.path.exists(img_fn):
            os.unlink(img_fn)
        if os.path.exists(eps_fn):
            os.unlink(eps_fn)
        raise EPSError('Could not run conversion process.')
    if os.path.exists(img_fn):
        os.unlink(img_fn)


def load_image_pil(img_fn, greyscale, eps_fn):
    """Use PIL to generate EPS."""
    from PIL import Image
    import traceback
    try:
        im = Image.open(img_fn)
        format = im.format
        if greyscale and im.mode not in ("1", "L"):
            im = im.convert("L")
        if not greyscale and im.mode == "P":
            im = im.convert("RGB")
        im.save(eps_fn, "EPS")
    except:
        traceback.print_exc()
        print("Exception printed from printing.epstools.load_image_pil()",
            file=sys.stderr)
        raise


def load_eps(eps_fn):
    """Load an EPS image.

    The bounding box is extracted and stored together with the data in an
    EPSImage object.  If a PostScript `showpage' command is obvious in the
    file, it is removed.
    """
    with open(eps_fn) as fp:
        lines = fp.readlines()
    try: lines.remove('showpage\n')
    except: pass                        # o.k. if not found
    bbox = load_bounding_box(lines)
    return EPSImage(''.join(lines), bbox)


def load_bounding_box(lines):
    """Determine bounding box for EPS image given as sequence of text lines.
    """
    bbox = None
    for line in lines:
        if len(line) > 21 and line[:15].lower() == '%%boundingbox: ':
            bbox = tuple(map(int, line[15:].split()))
            break
    if not bbox:
        raise EPSError('Bounding box not specified.')
    return bbox


def convert_gif_to_eps(cog, giffile, epsfile):
    """Convert GIF to EPS using specified conversion.

    The EPS image is stored in `epsfile' if possible, otherwise a temporary
    file is created.  The name of the file created is returned.
    """
    if ('gif', cog) not in image_converters:
        raise EPSError("No conversion defined for {} GIFs.".format(cog))
    try:
        fp = open(epsfile, 'w')
    except IOError:
        import tempfile
        filename = tempfile.mktemp()
    else:
        filename = epsfile
        fp.close()
    img_command = image_converters[('gif', cog)]
    img_command = img_command.format(i=giffile, o=filename)
    try:
        if os.system(img_command + ' 2>/dev/null'):
            if os.path.exists(filename):
                os.unlink(filename)
            raise EPSError('Error converting image to EPS.')
    except BaseException as err:
        if os.path.exists(filename):
            os.unlink(filename)
        raise EPSError('Could not run conversion process: {}.'.format(
                       type(err).__name__))
    return filename
