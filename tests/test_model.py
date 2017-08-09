import csv
import os.path

import keras
import keras_resnet.models
import numpy
import pkg_resources
import pytest

import deepometry.image.iterator
import deepometry.model


@pytest.fixture()
def resource_dir(tmpdir):
    directory = tmpdir.mkdir("deepometry")

    directory.mkdir("data")

    return directory


def test_init(resource_dir, mocker):
    resources = mocker.patch("pkg_resources.resource_filename")
    resources.side_effect = lambda _, filename: str(resource_dir.join(filename))

    model = deepometry.model.Model(name="ResNet50", shape=(48, 48, 3), units=4)

    assert model.name == "ResNet50"

    assert keras.backend.int_shape(model.model.input) == (None, 48, 48, 3)

    assert keras.backend.int_shape(model.model.output) == (None, 4)


def test_compile(resource_dir, mocker):
    resources = mocker.patch("pkg_resources.resource_filename")
    resources.side_effect = lambda _, filename: str(resource_dir.join(filename))

    model = deepometry.model.Model(name="ResNet50", shape=(48, 48, 3), units=4)
    model.compile()

    assert model.model.loss == "categorical_crossentropy"

    assert model.model.metrics == ["accuracy"]

    assert isinstance(model.model.optimizer, keras.optimizers.Adam)


def test_fit(resource_dir, mocker):
    numpy.random.seed(53)

    x = numpy.random.randint(256, size=(100, 48, 48, 3))
    y = numpy.random.randint(4, size=(100,))

    with mocker.patch("keras_resnet.models.ResNet50") as model_mock:
        keras_resnet.models.ResNet50.return_value = model_mock

        resources = mocker.patch("pkg_resources.resource_filename")
        resources.side_effect = lambda _, filename: str(resource_dir.join(filename))

        model = deepometry.model.Model(name="ResNet50", shape=(48, 48, 3), units=4)
        model.compile()
        model.fit(
            x,
            y,
            batch_size=10,
            epochs=1,
            validation_split=0.1,
            verbose=0
        )

        model_mock.fit_generator.assert_called_once_with(
            callbacks=mocker.ANY,
            epochs=1,
            generator=mocker.ANY,
            steps_per_epoch=9,
            validation_data=mocker.ANY,
            validation_steps=1,
            verbose=0
        )

        _, kwargs = model_mock.fit_generator.call_args

        assert os.path.exists(
            pkg_resources.resource_filename(
                "deepometry",
                os.path.join("data", model.name, "means.csv")
            )
        )

        # callbacks
        callbacks = kwargs["callbacks"]
        assert len(callbacks) == 4

        assert isinstance(callbacks[0], keras.callbacks.CSVLogger)
        assert callbacks[0].filename == pkg_resources.resource_filename(
            "deepometry",
            os.path.join("data", model.name, "training.csv")
        )

        assert isinstance(callbacks[1], keras.callbacks.EarlyStopping)

        assert isinstance(callbacks[2], keras.callbacks.ModelCheckpoint)
        assert callbacks[2].filepath == pkg_resources.resource_filename(
            "deepometry",
            os.path.join("data", model.name, "checkpoint.hdf5")
        )

        assert isinstance(callbacks[3], keras.callbacks.ReduceLROnPlateau)

        # generator
        generator = kwargs["generator"]
        assert isinstance(generator, deepometry.image.iterator.NumpyArrayIterator)
        assert generator.batch_size == 10
        assert generator.x.shape == (90, 48, 48, 3)
        assert generator.image_data_generator.height_shift_range == 0.5
        assert generator.image_data_generator.horizontal_flip == True
        assert generator.image_data_generator.rotation_range == 180
        assert generator.image_data_generator.vertical_flip == True
        assert generator.image_data_generator.width_shift_range == 0.5

        x_train = generator.x
        sample = x_train[0]

        expected = numpy.empty((48, 48, 3))
        expected[:, :, 0] = sample[:, :, 0] - numpy.mean(x_train[:, :, :, 0])
        expected[:, :, 1] = sample[:, :, 1] - numpy.mean(x_train[:, :, :, 1])
        expected[:, :, 2] = sample[:, :, 2] - numpy.mean(x_train[:, :, :, 2])

        actual = generator.image_data_generator.preprocessing_function(sample)

        numpy.testing.assert_array_almost_equal(actual, expected, decimal=5)

        # validation_data
        validation_data = kwargs["validation_data"]
        assert isinstance(validation_data, deepometry.image.iterator.NumpyArrayIterator)
        assert validation_data.batch_size == 10
        assert validation_data.x.shape == (10, 48, 48, 3)
        assert validation_data.image_data_generator.height_shift_range == 0.5
        assert validation_data.image_data_generator.horizontal_flip == True
        assert validation_data.image_data_generator.rotation_range == 180
        assert validation_data.image_data_generator.vertical_flip == True
        assert validation_data.image_data_generator.width_shift_range == 0.5

        x_valid = validation_data.x
        sample = x_valid[0]

        expected = numpy.empty((48, 48, 3))
        expected[:, :, 0] = sample[:, :, 0] - numpy.mean(x_train[:, :, :, 0])
        expected[:, :, 1] = sample[:, :, 1] - numpy.mean(x_train[:, :, :, 1])
        expected[:, :, 2] = sample[:, :, 2] - numpy.mean(x_train[:, :, :, 2])

        actual = generator.image_data_generator.preprocessing_function(sample)

        numpy.testing.assert_array_almost_equal(actual, expected, decimal=5)


def test_evaluate(resource_dir, mocker):
    x = numpy.random.randint(256, size=(100, 48, 48, 3)).astype(numpy.float64)
    y = numpy.random.randint(4, size=(100,))

    resource_dir.mkdir(os.path.join("data", "ResNet50"))
    meanscsv = str(resource_dir.join(os.path.join("data", "ResNet50", "means.csv")))
    with open(meanscsv, "w") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([125.3, 127.12, 121.9])

    expected_samples = x.copy()
    expected_samples[:, :, :, 0] -= 125.3
    expected_samples[:, :, :, 1] -= 127.12
    expected_samples[:, :, :, 2] -= 121.9

    expected_targets = keras.utils.to_categorical(y, 4)

    with mocker.patch("keras_resnet.models.ResNet50") as model_mock:
        keras_resnet.models.ResNet50.return_value = model_mock

        resources = mocker.patch("pkg_resources.resource_filename")
        resources.side_effect = lambda _, filename: str(resource_dir.join(filename))

        model = deepometry.model.Model(name="ResNet50", shape=(48, 48, 3), units=4)
        model.compile()
        model.evaluate(
            x,
            y,
            batch_size=10,
            verbose=0
        )

        model_mock.load_weights.assert_called_once_with(
            pkg_resources.resource_filename("deepometry", os.path.join("data", "ResNet50", "checkpoint.hdf5"))
        )

        model_mock.evaluate.assert_called_once_with(
            x=mocker.ANY,
            y=mocker.ANY,
            batch_size=10,
            verbose=0
        )

        _, kwargs = model_mock.evaluate.call_args

        samples = kwargs["x"]
        assert samples.shape == expected_samples.shape
        numpy.testing.assert_array_equal(samples, expected_samples)

        targets = kwargs["y"]
        assert targets.shape == expected_targets.shape
        numpy.testing.assert_array_equal(targets, expected_targets)
