import json
import numpy as np
from .parameter_set import ParameterSet, ClassWithParameterSet, Parameter, TYPE_INTRINSIC


class CameraProjection(ClassWithParameterSet):
    focallength_px = 0
    offset_x = 0
    offset_y = 0

    def __init__(self, focallength_mm=None, image_width_px=None, image_height_px=None, image=None,
                 sensor_width_mm=None, sensor_height_mm=None, sensor=None, view_x_deg=None, view_y_deg=None):
        if sensor is not None:
            sensor_width_mm, sensor_height_mm = sensor
        if image is not None:
            try:
                image_height_px, image_width_px = image.shape[:2]
            except AttributeError:
                image_width_px, image_height_px = image
        self.parameters = ParameterSet(
            # the intrinsic parameters
            focallength_mm=Parameter(focallength_mm, default=14, type=TYPE_INTRINSIC),  # the focal length in mm
            image_height_px=Parameter(image_height_px, default=3456, type=TYPE_INTRINSIC),  # the image height in px
            image_width_px=Parameter(image_width_px, default=4608, type=TYPE_INTRINSIC),  # the image width in px
            sensor_height_mm=Parameter(sensor_height_mm, default=13.0, type=TYPE_INTRINSIC),  # the sensor height in mm
            sensor_width_mm=Parameter(sensor_width_mm, default=17.3, type=TYPE_INTRINSIC),  # the sensor width in mm
        )
        if view_x_deg is not None or view_y_deg is not None:
            self.focallength_mm = self.fieldOfViewToFocallength(view_x_deg, view_y_deg)
        for name in self.parameters.parameters:
            self.parameters.parameters[name].callback = self._initIntrinsicMatrix
        self._initIntrinsicMatrix()

    def __str__(self):
        string = ""
        string += "  intrinsic (%s):\n" % type(self).__name__
        string += "    f:\t\t%.1f mm\n    sensor:\t%.2f×%.2f mm\n    image:\t%d×%d px\n" % (
            self.parameters.focallength_mm, self.parameters.sensor_width_mm, self.parameters.sensor_height_mm,
            self.parameters.image_width_px, self.parameters.image_height_px)
        return string

    def _initIntrinsicMatrix(self):
        # normalize the focal length by the sensor width and the image_width
        self.mm_per_px = self.parameters.sensor_width_mm / self.parameters.image_width_px
        self.focallength_px = self.parameters.focallength_mm / self.mm_per_px
        self.offset_x = self.parameters.image_width_px / 2
        self.offset_y = self.parameters.image_height_px / 2

    def save(self, filename):
        keys = self.parameters.parameters.keys()
        export_dict = {key: getattr(self, key) for key in keys}
        with open(filename, "w") as fp:
            fp.write(json.dumps(export_dict))

    def load(self, filename):
        with open(filename, "r") as fp:
            variables = json.loads(fp.read())
        for key in variables:
            setattr(self, key, variables[key])


class RectilinearProjection(CameraProjection):

    def getRay(self, points, normed=False):
        # ensure that the points are provided as an array
        points = np.array(points)
        # set z=focallenth and solve the other equations for x and y
        ray = np.array([points[..., 0] - self.offset_x,
                        points[..., 1] - self.offset_y,
                        np.zeros(points[..., 1].shape) + self.focallength_px]).T
        # norm the ray if desired
        if normed:
            ray /= np.linalg.norm(ray, axis=-1)[..., None]
        # return the ray
        return -ray

    def imageFromCamera(self, points):
        """
                        x                              y
            x_im = f * --- + offset_x      y_im = f * --- + offset_y
                        z                              z
        """
        points = np.array(points)
        # set small z distances to 0
        points[np.abs(points[..., 2]) < 1e-10] = 0
        # transform the points
        transformed_points = np.array([points[..., 0] * self.focallength_px / points[..., 2] + self.offset_x,
                                       points[..., 1] * self.focallength_px / points[..., 2] + self.offset_y]).T
        transformed_points[points[..., 2] > 0] = np.nan
        return transformed_points

    def getFieldOfView(self):
        return np.rad2deg(2 * np.arctan(self.sensor_width_mm / (2 * self.focallength_mm))), \
               np.rad2deg(2 * np.arctan(self.sensor_height_mm / (2 * self.focallength_mm)))

    def fieldOfViewToFocallength(self, view_x=None, view_y=None):
        if view_x is not None:
            return self.sensor_width_mm / (2 * np.tan(np.deg2rad(view_x) / 2))
        else:
            return self.sensor_height_mm / (2 * np.tan(np.deg2rad(view_y) / 2))


class CylindricalProjection(CameraProjection):

    def getRay(self, points, normed=False):
        # ensure that the points are provided as an array
        points = np.array(points)
        # set r=1 and solve the other equations for x and y
        r = 1
        alpha = (points[..., 0] - self.offset_x) / self.focallength_px
        x = np.sin(alpha) * r
        z = np.cos(alpha) * r
        y = r * (points[..., 1] - self.offset_y) / self.focallength_px
        # compose the ray
        ray = np.array([x, y, z]).T
        # norm the ray if desired
        if normed:
            ray /= np.linalg.norm(ray, axis=-1)[..., None]
        # return the rey
        return -ray

    def imageFromCamera(self, points):
        """
                             ( x )                                  y
            x_im = f * arctan(---) + offset_x      y_im = f * --------------- + offset_y
                             ( z )                            sqrt(x**2+z**2)
        """
        # ensure that the points are provided as an array
        points = np.array(points)
        # set small z distances to 0
        points[np.abs(points[..., 2]) < 1e-10] = 0
        # transform the points
        transformed_points = np.array(
            [self.focallength_px * np.arctan2(-points[..., 0], -points[..., 2]) + self.offset_x,
             -self.focallength_px * points[..., 1] / np.linalg.norm(points[..., [0, 2]], axis=-1) + self.offset_y]).T
        # ignore points that are behind the camera
        transformed_points[points[..., 2] > 0] = np.nan
        # ensure that points' x values are also nan when the y values are nan
        transformed_points[np.isnan(transformed_points[..., 1])] = np.nan
        # return the points
        return transformed_points

    def getFieldOfView(self):
        return np.rad2deg(self.sensor_width_mm / self.focallength_mm), \
               np.rad2deg(2 * np.arctan(self.sensor_height_mm / (2 * self.focallength_mm)))

    def fieldOfViewToFocallength(self, view_x=None, view_y=None):
        if view_x is not None:
            return self.sensor_width_mm / np.deg2rad(view_x)
        else:
            return self.sensor_height_mm / (2 * np.tan(np.deg2rad(view_y) / 2))


class EquirectangularProjection(CameraProjection):

    def getRay(self, points, normed=False):
        # ensure that the points are provided as an array
        points = np.array(points)
        # set r=1 and solve the other equations for x and y
        r = 1
        alpha = (points[..., 0] - self.offset_x) / self.focallength_px
        x = np.sin(alpha) * r
        z = np.cos(alpha) * r
        y = r * np.tan((points[..., 1] - self.offset_y) / self.focallength_px)
        # compose the ray
        ray = np.array([x, y, z]).T
        # norm the ray if desired
        if normed:
            ray /= np.linalg.norm(ray, axis=-1)[..., None]
        # return the rey
        return -ray

    def imageFromCamera(self, points):
        """
                             ( x )                                  (       y       )
            x_im = f * arctan(---) + offset_x      y_im = f * arctan(---------------) + offset_y
                             ( z )                                  (sqrt(x**2+z**2))
        """
        # ensure that the points are provided as an array
        points = np.array(points)
        # set small z distances to 0
        points[np.abs(points[..., 2]) < 1e-10] = 0
        # transform the points
        transformed_points = np.array([self.focallength_px * np.arctan(points[..., 0] / points[..., 2]) + self.offset_x,
                                       -self.focallength_px * np.arctan(points[..., 1] / np.sqrt(
                                           points[..., 0] ** 2 + points[..., 2] ** 2)) + self.offset_y]).T
        # ignore points that are behind the camera
        transformed_points[points[..., 2] > 0] = np.nan
        # return the points
        return transformed_points

    def getFieldOfView(self):
        return np.rad2deg(self.sensor_width_mm / self.focallength_mm),\
               np.rad2deg(self.sensor_height_mm / self.focallength_mm)

    def fieldOfViewToFocallength(self, view_x=None, view_y=None):
        if view_x is not None:
            return self.sensor_width_mm / np.deg2rad(view_x)
        else:
            return self.sensor_height_mm / np.deg2rad(view_y)