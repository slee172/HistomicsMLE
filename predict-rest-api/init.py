"""
Init class

Initialize model(VGG).
Load pca information
"""
from tensorflow.keras.applications.vgg16 import VGG16
from tensorflow.keras.models import Model

class Init():

    def __init__(self):

        # initialize constants used for HistomicsML
        self.VGG_MODEL = VGG16(include_top=True, weights='imagenet')
        self.FC1_MODEL = Model(inputs=self.VGG_MODEL.input, outputs=self.VGG_MODEL.get_layer('fc1').output)
