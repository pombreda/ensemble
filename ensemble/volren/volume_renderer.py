from mayavi.sources.vtk_data_source import VTKDataSource
from mayavi.tools.tools import add_dataset
from traits.api import CInt, Instance, List
from tvtk.api import tvtk

from ensemble.ctf.piecewise import PiecewiseFunction
from .volume_3d import Volume3D, volume3d
from .volume_data import VolumeData
from .volume_scene_member import ABCVolumeSceneMember

CLIP_MAX = 512


class VolumeRenderer(ABCVolumeSceneMember):
    # The data to plot
    data = Instance(VolumeData)

    # The mayavi data source for the volume data
    data_source = Instance(VTKDataSource)

    # The mayavi volume renderer object
    volume = Instance(Volume3D)

    # The minimum and maximum displayed intensity values.
    vmin = CInt(0)
    vmax = CInt(255)

    # The transfer function components
    opacities = Instance(PiecewiseFunction)
    colors = Instance(PiecewiseFunction)

    # Clip plane positions
    clip_bounds = List(CInt)

    # -------------------------------------------------------------------------
    # ABCVolumeSceneMember interface
    # -------------------------------------------------------------------------

    def add_actors_to_scene(self, scene_model):
        sf = add_dataset(self.data.resampled_image_data,
                         figure=scene_model.mayavi_scene)
        self.data_source = sf
        self.volume = volume3d(sf, figure=scene_model.mayavi_scene)
        self._setup_volume()

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------

    def set_transfer_function(self, colors=None, opacities=None):
        """ Update the volume mapper's transfer function.
        """
        lerp = lambda x: self.vmin + x * (self.vmax - self.vmin)

        if colors is not None:
            self.colors = colors
        if opacities is not None:
            self.opacities = opacities

        ctf = tvtk.ColorTransferFunction()
        for color in self.colors.items():
            ctf.add_rgb_point(lerp(color[0]), *(color[1:]))

        otf = tvtk.PiecewiseFunction()
        alphas = self.opacities.items()
        for i, alpha in enumerate(alphas):
            x = alpha[0]
            if i > 0:
                # Look back one item. VTK doesn't like exact vertical jumps, so
                # we need to jog a value that is exactly equal by a little bit.
                if alphas[i-1][0] == alpha[0]:
                    x += 1e-8
            otf.add_point(lerp(x), alpha[1])

        self._set_volume_ctf(ctf, otf)

    # -------------------------------------------------------------------------
    # Default values
    # -------------------------------------------------------------------------

    def _clip_bounds_default(self):
        return [0, CLIP_MAX, 0, CLIP_MAX, 0, CLIP_MAX]

    # -------------------------------------------------------------------------
    # Traits notifications
    # -------------------------------------------------------------------------

    def _data_changed(self):
        self.vmin = self.data.raw_data.min()
        self.vmax = self.data.raw_data.max()

        if self.data_source is not None:
            image_data = self.data.resampled_image_data
            self.data_source.data = image_data
            self.data_source.update()
            self._setup_volume()

    def _clip_bounds_changed(self):
        self._set_volume_clip_planes()

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    def _setup_volume(self):
        self.volume.volume_mapper.trait_set(sample_distance=0.2)
        self.volume.volume_property.trait_set(shade=False)
        self._set_volume_clip_planes()
        self.set_transfer_function()

    def _set_volume_clip_planes(self):
        bounds = [b/CLIP_MAX for b in self.data.bounds]
        mn = [bounds[i]*pos for i, pos in enumerate(self.clip_bounds[::2])]
        mx = [bounds[i]*pos for i, pos in enumerate(self.clip_bounds[1::2])]
        planes = tvtk.Planes()
        # The planes need to be inside out to serve as clipping planes
        planes.set_bounds(mx[0], mn[0],
                          mx[1], mn[1],
                          mx[2], mn[2])
        # Set them as the clipping planes for the volume mapper
        self.volume.volume.mapper.clipping_planes = planes

    def _set_volume_ctf(self, ctf, otf):
        if self.volume is not None:
            vp = self.volume.volume_property
            vp.set_scalar_opacity(otf)
            vp.set_color(ctf)
            self.volume._update_ctf_fired()
