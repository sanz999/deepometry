import hashlib
import os.path
import time

import bioformats.formatreader
import javabridge
import numpy
import scipy.stats
import skimage.exposure
import skimage.util


def parse(pathname, output_directory, size, channels=None):
    """
    Convert an .CIF image file to a NumPy array. The javabridge JVM is required:

        import bioformats
        import deepometry.parse
        import javabridge


        javabridge.start_vm(class_path=bioformats.JARS)

        images = deepometry.parse.parse("cells.cif", 48, [0, 5, 6])

    :param pathname: Image pathname.
    :param output_directory: Location where parsed images are saved.
    :param size: Final image dimensions (size, size, channels).
    :param channels: Image channels to extract.
    """
    ext = os.path.splitext(pathname)[-1].lower()

    if ext == ".cif":
        return _parse_cif(pathname, output_directory, size, channels)

    raise NotImplementedError("Unsupported file format: {}".format(ext))


def _parse_cif(pathname, output_directory, size, channels):
    reader = bioformats.formatreader.get_image_reader("tmp", path=pathname)

    image_count = javabridge.call(reader.metadata, "getImageCount", "()I")

    # TODO: An overflow error occurs when reading image 190663 and above. :(
    image_count = numpy.min((image_count, 190662))

    if channels is None:
        channel_count = javabridge.call(reader.metadata, "getChannelCount", "(I)I", 0)

        channels = range(channel_count)

    for image_index in range(0, image_count, 2):
        image = reader.read(series=image_index)

        parsed_image = numpy.empty((size, size, len(channels)), dtype=numpy.uint8)

        for (channel_index, channel) in enumerate(channels):
            parsed_image[:, :, channel_index] = _rescale(_resize(image[:, :, channel], size))

        output_pathname = os.path.join(
            output_directory,
            "{}.npy".format(hashlib.md5(str(time.time()).encode("utf8")).hexdigest())
        )

        numpy.save(output_pathname, parsed_image)

    return True


def _rescale(image):
    vmin, vmax = scipy.stats.scoreatpercentile(image, (0.5, 99.5))

    return skimage.exposure.rescale_intensity(image, in_range=(vmin, vmax), out_range=numpy.uint8).astype(numpy.uint8)


def _resize(image, size):
    column_adjust = size - image.shape[0]
    column_adjust_start = int(numpy.floor(column_adjust / 2.0))
    column_adjust_end = int(numpy.ceil(column_adjust / 2.0))

    row_adjust = size - image.shape[1]
    row_adjust_start = int(numpy.floor(row_adjust / 2.0))
    row_adjust_end = int(numpy.ceil(row_adjust / 2.0))

    resized = skimage.util.crop(
        image,
        (
            numpy.abs(numpy.minimum((column_adjust_start, column_adjust_end), (0, 0))),
            numpy.abs(numpy.minimum((row_adjust_start, row_adjust_end), (0, 0)))
        )
    )

    return _pad(
        resized,
        (
            numpy.maximum((column_adjust_start, column_adjust_end), (0, 0)),
            numpy.maximum((row_adjust_start, row_adjust_end), (0, 0))
        )
    )


def _pad(image, pad_width):
    # TODO: More robust background sampling. Ideas:
    #   - Sample all 4 corners, discarding outliers (possible artifacts in corner),
    #   - Sample masked pixels,
    #   - Assuming a bimodal intensity distribution, sample the mean and standard deviation from the background
    #     distribution.
    sample = image[-10:, -10:]

    return numpy.pad(image, pad_width, _pad_normal, mean=numpy.mean(sample), std=numpy.std(sample))


def _pad_normal(vector, pad_width, iaxis, kwargs):
    if pad_width[0] > 0:
        vector[:pad_width[0]] = numpy.random.normal(kwargs["mean"], kwargs["std"], vector[:pad_width[0]].shape)

    if pad_width[1] > 0:
        vector[-pad_width[1]:] = numpy.random.normal(kwargs["mean"], kwargs["std"], vector[-pad_width[1]:].shape)

    return vector
