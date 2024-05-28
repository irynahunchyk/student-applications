import re
import numpy as np
import matplotlib.pyplot as plt

from pathlib import Path
import os
# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.models import load_model

import json
import cv2 as cv


#                   Load the data

with open('../../SingleLineImages/Train/ClearImages/clear_images_data.json') as json_file:
    DATA = json.load(json_file)


def take_clear_image_text(clear_image_name):
    res = ''
    clear_image_data = DATA[clear_image_name]

    for word_data in clear_image_data:
        word = str(word_data['word'])
        if word.find('\n') == -1:
            res += word + ' '
        else:
            res += word
    return res


# Path to the data directory
data_dir = Path('../../SingleLineImages/Train/DegradedImages/')

# Get list of all the images
images = list(map(str, list(data_dir.glob("*.png"))))
images = sorted(images, key=lambda x: int(''.join(re.findall('\d+', x))))
labels = [take_clear_image_text('clear_image'+str(i)+'.png') for i in range(len(images))]

# images = images[:5000]
# labels = labels[:5000]

all_text = ''
for label in labels:
    all_text += label
characters = sorted(list(set(all_text)))

# characters = ['\n', ' ', '!', '"', "'", '(', ')', '*', ',', '-', '.', '/',
# '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', ':', ';', '=', '?',
# 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
# 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']


print("Number of images found: ", len(images))
print("Number of labels found: ", len(labels))
print("Number of unique characters: ", len(characters))
print("Characters present: ", characters)


#                   Preprocessing

# Batch size for training and validation
batch_size = 16

# Desired image dimensions
img_width = 256
img_height = 64
# Maximum length of any captcha in the dataset
max_label_len = max([len(label) for label in labels])

for i in range(len(labels)):
    labels[i] += ' ' * (max_label_len - len(labels[i]))


# Mapping characters to integers
char_to_num = layers.experimental.preprocessing.StringLookup(
    vocabulary=list(characters), num_oov_indices=0, mask_token=None
)

# Mapping integers back to original characters
num_to_char = layers.experimental.preprocessing.StringLookup(
    vocabulary=char_to_num.get_vocabulary(), mask_token=None, invert=True
)


def split_data(images, labels, train_size=0.9, shuffle=True):
    # 1. Get the total size of the dataset
    size = len(images)
    # 2. Make an indices array and shuffle it, if required
    indices = np.arange(size)
    if shuffle:
        np.random.shuffle(indices)
    # 3. Get the size of training samples
    train_samples = int(size * train_size)
    # 4. Split data into training and validation sets
    x_train, y_train = images[indices[:train_samples]], labels[indices[:train_samples]]
    x_valid, y_valid = images[indices[train_samples:]], labels[indices[train_samples:]]
    return x_train, x_valid, y_train, y_valid


# Splitting data into training and validation sets
x_train, x_valid, y_train, y_valid = split_data(np.array(images), np.array(labels))


def encode_single_sample(img_path, label):
    # 1. Read image
    img = tf.io.read_file(img_path)
    # 2. Decode and convert to grayscale
    img = tf.io.decode_png(img, channels=1)
    # 3. Convert to float32 in [0, 1] range
    img = tf.image.convert_image_dtype(img, tf.float32)
    # 4. Resize to the desired size
    img = tf.image.resize(img, [img_height, img_width])
    # 5. Transpose the image because we want the time
    # dimension to correspond to the width of the image.
    img = tf.transpose(img, perm=[1, 0, 2])
    # 6. Map the characters in label to numbers
    label = char_to_num(tf.strings.unicode_split(label, input_encoding="UTF-8"))
    # 7. Return a dict as our model is expecting two inputs
    return {"image": img, "label": label}


#                   Create Dataset objects

train_dataset = tf.data.Dataset.from_tensor_slices((x_train, y_train))
train_dataset = (
    train_dataset.map(
        encode_single_sample, num_parallel_calls=tf.data.experimental.AUTOTUNE
    )
    .batch(batch_size)
    .prefetch(buffer_size=tf.data.experimental.AUTOTUNE)
)

validation_dataset = tf.data.Dataset.from_tensor_slices((x_valid, y_valid))
validation_dataset = (
    validation_dataset.map(
        encode_single_sample, num_parallel_calls=tf.data.experimental.AUTOTUNE
    )
    .batch(batch_size)
    .prefetch(buffer_size=tf.data.experimental.AUTOTUNE)
)


#                   Visualize the data
'''
for batch in train_dataset:
    images = batch["image"]
    labels = batch["label"]
    for i in range(batch_size):
        img = (images[i] * 255).numpy().astype("uint8")
        label = tf.strings.reduce_join(num_to_char(labels[i])).numpy().decode("utf-8")
        # print(label)
        # cv.imshow('img', img[:, :, 0].T)
        # cv.waitKey()
'''
_, ax = plt.subplots(1, 8, figsize=(10, 5))
for batch in train_dataset.take(1):
    images = batch["image"]
    labels = batch["label"]
    for i in range(8):
        img = (images[i] * 255).numpy().astype("uint8")
        title = tf.strings.reduce_join(num_to_char(labels[i])).numpy().decode("utf-8")
        ax[i].imshow(img[:, :, 0].T, cmap="gray")
        ax[i].set_title(title, size=4)
        ax[i].axis("off")
plt.show()


#                   Model

class CTCLayer(layers.Layer):
    def __init__(self, name=None, **kwargs):
        super(CTCLayer, self).__init__(name=name)
        super(CTCLayer, self).__init__(**kwargs)
        self.loss_fn = keras.backend.ctc_batch_cost

    def get_config(self):
        config = super(CTCLayer, self).get_config()
        return config

    @classmethod
    def from_config(cls, config):
        return cls(**config)

    def call(self, y_true, y_pred):
        # Compute the training-time loss value and add it
        # to the layer using `self.add_loss()`.
        batch_len = tf.cast(tf.shape(y_true)[0], dtype="int64")
        input_length = tf.cast(tf.shape(y_pred)[1], dtype="int64")
        label_length = tf.cast(tf.shape(y_true)[1], dtype="int64")

        input_length = input_length * tf.ones(shape=(batch_len, 1), dtype="int64")
        label_length = label_length * tf.ones(shape=(batch_len, 1), dtype="int64")

        loss = self.loss_fn(y_true, y_pred, input_length, label_length)
        self.add_loss(loss)

        # At test time, just return the computed predictions
        return y_pred


def build_model():
    # Inputs to the model
    input_img = layers.Input(
        shape=(img_width, img_height, 1), name="image", dtype="float32"
    )
    labels = layers.Input(name="label", shape=(None,), dtype="float32")

    # First conv block
    x = layers.Conv2D(
        32,
        (3, 3),
        activation="relu",
        kernel_initializer="he_normal",
        padding="same",
        name="Conv1",
    )(input_img)
    x = layers.MaxPooling2D((2, 2), name="pool1")(x)

    # Second conv block
    x = layers.Conv2D(
        64,
        (3, 3),
        activation="relu",
        kernel_initializer="he_normal",
        padding="same",
        name="Conv2",
    )(x)
    x = layers.MaxPooling2D((2, 2), name="pool2")(x)

    # Third conv block
    x = layers.Conv2D(
        64,
        (3, 3),
        activation="relu",
        kernel_initializer="he_normal",
        padding="same",
        name="Conv3",
    )(x)
    x = layers.MaxPooling2D((2, 2), name="pool3")(x)

    # We have used two max pool with pool size and strides 2.
    # Hence, downsampled feature maps are 4x smaller.
    # The number of filters in the last layer is 64.
    # Reshape accordingly before passing the output to the RNN part of the model
    new_shape = ((img_width // 8) * 2, (img_height // 8) * 32)
    x = layers.Reshape(target_shape=new_shape, name="reshape")(x)
    x = layers.Dense(64, activation="relu", name="dense1")(x)
    x = layers.Dropout(0.2)(x)

    # RNNs
    x = layers.Bidirectional(layers.LSTM(128, return_sequences=True, dropout=0.25))(x)
    x = layers.Bidirectional(layers.LSTM(64, return_sequences=True, dropout=0.25))(x)

    # Output layer
    x = layers.Dense(len(characters) + 1, activation="softmax", name="dense2")(x)

    # Add CTC layer for calculating CTC loss at each step
    output = CTCLayer(name="ctc_loss")(labels, x)

    # Define the model
    model = keras.models.Model(
        inputs=[input_img, labels], outputs=output, name="ocr_model_v1"
    )
    # Optimizer
    opt = keras.optimizers.Adam()
    # Compile the model and return
    model.compile(optimizer=opt)
    return model


# Get the model
model = build_model()
model.summary()


#                   Training

epochs = 500
early_stopping_patience = 100
# Add early stopping
early_stopping = keras.callbacks.EarlyStopping(
    monitor="val_loss", patience=early_stopping_patience, restore_best_weights=True
)

# Train the model
history = model.fit(
    train_dataset,
    epochs=epochs,
    callbacks=[early_stopping],
    validation_data=validation_dataset,
    verbose=1
)


#                   Saving the model

if os.path.isfile('models/keras_model_1.h5') is False:
    model.save('models/keras_model_1.h5')


'''
#                   Loading the model

model = load_model('./models/keras_model.h5', custom_objects={'CTCLayer': CTCLayer})
'''

#                   Inference

# Get the prediction model by extracting layers till the output layer
prediction_model = keras.models.Model(
    model.get_layer(name="image").input, model.get_layer(name="dense2").output
)
prediction_model.summary()


# A utility function to decode the output of the network
def decode_batch_predictions(pred):
    input_len = np.ones(pred.shape[0]) * pred.shape[1]
    # Use greedy search. For complex tasks, you can use beam search
    results = keras.backend.ctc_decode(pred, input_length=input_len, greedy=True)[0][0][:, :max_label_len]
    # Iterate over the results and get back the text
    output_text = []
    for res in results:
        res = tf.strings.reduce_join(num_to_char(res)).numpy().decode("utf-8")
        output_text.append(res)
    return output_text


#  Let's check results on some validation samples
for batch in validation_dataset.take(1):
    batch_images = batch["image"]
    batch_labels = batch["label"]

    preds = prediction_model.predict(batch_images)
    pred_texts = decode_batch_predictions(preds)

    orig_texts = []
    for label in batch_labels:
        label = tf.strings.reduce_join(num_to_char(label)).numpy().decode("utf-8")
        orig_texts.append(label)
    '''
    for i in range(len(pred_texts)):
        img = (batch_images[i, :, :, 0] * 255).numpy().astype(np.uint8)
        img = img.T
        print(pred_texts[i])
        cv.imshow('img', img)
        cv.waitKey()
    '''
    _, ax = plt.subplots(1, 8, figsize=(10, 5))
    for i in range(8):
        img = (batch_images[i, :, :, 0] * 255).numpy().astype(np.uint8)
        img = img.T
        label = tf.strings.reduce_join(num_to_char(batch_labels[i])).numpy().decode("utf-8")
        title = f"True:\n {label}\n\nPrediction:\n {pred_texts[i]}"
        ax[i].imshow(img, cmap="gray")
        ax[i].set_title(title, size=4)
        ax[i].axis("off")
plt.show()
