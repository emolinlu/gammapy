# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""Dark matter spectra."""

import numpy as np
import astropy.units as u
from astropy.table import Table
from gammapy.maps import Map, MapAxis, RegionGeom
from gammapy.modeling import Parameter
from gammapy.modeling.models import SpectralModel, TemplateNDSpectralModel
from gammapy.utils.scripts import make_path

__all__ = ["PrimaryFlux", "DarkMatterAnnihilationSpectralModel"]


class PrimaryFlux(TemplateNDSpectralModel):
    """DM-annihilation gamma-ray spectra.

    Based on the precomputed models by Cirelli et al. (2016). All available
    annihilation channels can be found there. The dark matter mass will be set
    to the nearest available value. The spectra will be available as
    `~gammapy.modeling.models.TemplateNDSpectralModel` for a chosen dark matter mass and
    annihilation channel. Using a `~gammapy.modeling.models.TemplateNDSpectralModel`
    allows the interpolation between different dark matter masses.

    Parameters
    ----------
    mDM : `~astropy.units.Quantity`
        Dark matter particle mass as rest mass energy.
    channel: str
        Annihilation channel. List available channels with `~gammapy.spectrum.PrimaryFlux.allowed_channels`.

    References
    ----------
    * `Marco et al. (2011), "PPPC 4 DM ID: a poor particle physicist cookbook for dark matter indirect detection"
      <https://ui.adsabs.harvard.edu/abs/2011JCAP...03..051C>`_
    * `Cirelli et al. (2016), "PPPC 4 DM ID: A Poor Particle Physicist Cookbook for Dark Matter Indirect Detection"
      <http://www.marcocirelli.net/PPPC4DMID.html>`_
    """

    channel_registry = {
        "eL": "eL",
        "eR": "eR",
        "e": "e",
        "muL": r"\[Mu]L",
        "muR": r"\[Mu]R",
        "mu": r"\[Mu]",
        "tauL": r"\[Tau]L",
        "tauR": r"\[Tau]R",
        "tau": r"\[Tau]",
        "q": "q",
        "c": "c",
        "b": "b",
        "t": "t",
        "WL": "WL",
        "WT": "WT",
        "W": "W",
        "ZL": "ZL",
        "ZT": "ZT",
        "Z": "Z",
        "g": "g",
        "gamma": r"\[Gamma]",
        "h": "h",
        "nu_e": r"\[Nu]e",
        "nu_mu": r"\[Nu]\[Mu]",
        "nu_tau": r"\[Nu]\[Tau]",
        "V->e": "V->e",
        "V->mu": r"V->\[Mu]",
        "V->tau": r"V->\[Tau]",
    }

    table_filename = "$GAMMAPY_DATA/dark_matter_spectra/AtProduction_gammas.dat"

    tag = ["PrimaryFlux", "dm-pf"]

    def __init__(self, mDM, channel):
        self.table_path = make_path(self.table_filename)
        if not self.table_path.exists():
            raise FileNotFoundError(
                f"\n\nFile not found: {self.table_filename}\n"
                "You may download the dataset needed with the following command:\n"
                "gammapy download datasets --src dark_matter_spectra"
            )
        else:
            self.table = Table.read(
                str(self.table_path),
                format="ascii.fast_basic",
                guess=False,
                delimiter=" ",
            )

        self.channel = channel

        # create RegionNDMap for channel

        masses = np.unique(self.table["mDM"])
        log10x = np.unique(self.table["Log[10,x]"])

        mass_axis = MapAxis.from_nodes(masses, name="mass", interp="log", unit="GeV")
        log10x_axis = MapAxis.from_nodes(log10x, name="energy_true")

        channel_name = self.channel_registry[self.channel]

        geom = RegionGeom(region=None, axes=[log10x_axis, mass_axis])
        region_map = Map.from_geom(
            geom=geom, data=self.table[channel_name].reshape(geom.data_shape)
        )

        interp_kwargs = {"extrapolate": True, "fill_value": 0, "values_scale": "lin"}
        super().__init__(region_map, interp_kwargs=interp_kwargs)
        self.mDM = mDM
        self.mass.frozen = True

    @property
    def mDM(self):
        """Dark matter mass."""
        return u.Quantity(self.mass.value, "GeV")

    @mDM.setter
    def mDM(self, mDM):
        unit = self.mass.unit
        _mDM = u.Quantity(mDM).to(unit)
        _mDM_val = _mDM.to_value(unit)

        min_mass = u.Quantity(self.mass.min, unit)
        max_mass = u.Quantity(self.mass.max, unit)

        if _mDM_val < self.mass.min or _mDM_val > self.mass.max:
            raise ValueError(
                f"The mass {_mDM} is out of the bounds of the model. Please choose a mass between {min_mass} < `mDM` < {max_mass}"
            )

        self.mass.value = _mDM_val

    @property
    def allowed_channels(self):
        """List of allowed annihilation channels."""
        return list(self.channel_registry.keys())

    @property
    def channel(self):
        """Annihilation channel as a string."""
        return self._channel

    @channel.setter
    def channel(self, channel):
        if channel not in self.allowed_channels:
            raise ValueError(
                f"Invalid channel: {channel}\nAvailable: {self.allowed_channels}\n"
            )
        else:
            self._channel = channel

    def evaluate(self, energy, **kwargs):
        """Evaluate the primary flux."""
        mass = {"mass": self.mDM}
        kwargs.update(mass)

        log10x = np.log10(energy / self.mDM)

        dN_dlogx = super().evaluate(log10x, **kwargs)
        dN_dE = dN_dlogx / (energy * np.log(10))
        return dN_dE


class DarkMatterAnnihilationSpectralModel(SpectralModel):
    r"""Dark matter annihilation spectral model.

    The gamma-ray flux is computed as follows:

    .. math::
        \frac{\mathrm d \phi}{\mathrm d E} =
        \frac{\langle \sigma\nu \rangle}{4\pi k m^2_{\mathrm{DM}}}
        \frac{\mathrm d N}{\mathrm dE} \times J(\Delta\Omega)

    Parameters
    ----------
    mass : `~astropy.units.Quantity`
        Dark matter mass.
    channel : str
        Annihilation channel for `~gammapy.astro.darkmatter.PrimaryFlux`, e.g. "b" for "bbar".
        See `PrimaryFlux.channel_registry` for more.
    scale : float
        Scale parameter for model fitting.
    jfactor : `~astropy.units.Quantity`
        Integrated J-Factor needed when `~gammapy.modeling.models.PointSpatialModel`
        is used.
    z: float
        Redshift value.
    k: int
        Type of dark matter particle (k:2 Majorana, k:4 Dirac).

    Examples
    --------
    This is how to instantiate a `DarkMatterAnnihilationSpectralModel` model::

        >>> import astropy.units as u
        >>> from gammapy.astro.darkmatter import DarkMatterAnnihilationSpectralModel

        >>> channel = "b"
        >>> massDM = 5000*u.Unit("GeV")
        >>> jfactor = 3.41e19 * u.Unit("GeV2 cm-5")
        >>> modelDM = DarkMatterAnnihilationSpectralModel(mass=massDM, channel=channel, jfactor=jfactor)  # noqa: E501

    References
    ----------
    `Marco et al. (2011), "PPPC 4 DM ID: a poor particle physicist cookbook for dark matter indirect detection"
    <https://ui.adsabs.harvard.edu/abs/2011JCAP...03..051C>`_
    """

    THERMAL_RELIC_CROSS_SECTION = 3e-26 * u.Unit("cm3 s-1")
    """Thermally averaged annihilation cross-section"""

    scale = Parameter(
        "scale",
        1,
        unit="",
        interp="log",
    )
    tag = ["DarkMatterAnnihilationSpectralModel", "dm-annihilation"]

    def __init__(self, mass, channel, scale=scale.quantity, jfactor=1, z=0, k=2):
        self.k = k
        self.z = z
        self.mass = u.Quantity(mass)
        self.channel = channel
        self.jfactor = u.Quantity(jfactor)
        self.primary_flux = PrimaryFlux(mass, channel=self.channel)
        super().__init__(scale=scale)

    def evaluate(self, energy, scale):
        """Evaluate dark matter annihilation model."""
        flux = (
            scale
            * self.jfactor
            * self.THERMAL_RELIC_CROSS_SECTION
            * self.primary_flux(energy=energy * (1 + self.z))
            / self.k
            / self.mass
            / self.mass
            / (4 * np.pi)
        )
        return flux

    def to_dict(self, full_output=False):
        """Convert to dictionary."""
        data = super().to_dict(full_output=full_output)
        data["spectral"]["channel"] = self.channel
        data["spectral"]["mass"] = self.mass.to_string()
        data["spectral"]["jfactor"] = self.jfactor.to_string()
        data["spectral"]["z"] = self.z
        data["spectral"]["k"] = self.k
        return data

    @classmethod
    def from_dict(cls, data):
        """Create spectral model from a dictionary.

        Parameters
        ----------
        data : dict
            Dictionary with model data.

        Returns
        -------
        model : `DarkMatterAnnihilationSpectralModel`
            Dark matter annihilation spectral model.
        """
        data = data["spectral"]
        data.pop("type")
        parameters = data.pop("parameters")
        scale = [p["value"] for p in parameters if p["name"] == "scale"][0]
        return cls(scale=scale, **data)


class DarkMatterDecaySpectralModel(SpectralModel):
    r"""Dark matter decay spectral model.

    The gamma-ray flux is computed as follows:

    .. math::
        \frac{\mathrm d \phi}{\mathrm d E} =
        \frac{\Gamma}{4\pi m_{\mathrm{DM}}}
        \frac{\mathrm d N}{\mathrm dE} \times J(\Delta\Omega)

    Parameters
    ----------
    mass : `~astropy.units.Quantity`
        Dark matter mass.
    channel : str
        Annihilation channel for `~gammapy.astro.darkmatter.PrimaryFlux`, e.g. "b" for "bbar".
        See `PrimaryFlux.channel_registry` for more.
    scale : float
        Scale parameter for model fitting
    jfactor : `~astropy.units.Quantity`
        Integrated J-Factor needed when `~gammapy.modeling.models.PointSpatialModel`
        is used.
    z: float
        Redshift value.

    Examples
    --------
    This is how to instantiate a `DarkMatterAnnihilationSpectralModel` model::

        >>> import astropy.units as u
        >>> from gammapy.astro.darkmatter import DarkMatterDecaySpectralModel

        >>> channel = "b"
        >>> massDM = 5000*u.Unit("GeV")
        >>> jfactor = 3.41e19 * u.Unit("GeV cm-2")
        >>> modelDM = DarkMatterDecaySpectralModel(mass=massDM, channel=channel, jfactor=jfactor)  # noqa: E501

    References
    ----------
    `Marco et al. (2011), "PPPC 4 DM ID: a poor particle physicist cookbook for dark matter indirect detection"
    <https://ui.adsabs.harvard.edu/abs/2011JCAP...03..051C>`_
    """

    LIFETIME_AGE_OF_UNIVERSE = 4.3e17 * u.Unit("s")
    """Use age of univserse as lifetime"""

    scale = Parameter(
        "scale",
        1,
        unit="",
        interp="log",
    )

    tag = ["DarkMatterDecaySpectralModel", "dm-decay"]

    def __init__(self, mass, channel, scale=scale.quantity, jfactor=1, z=0):
        self.z = z
        self.mass = u.Quantity(mass)
        self.channel = channel
        self.jfactor = u.Quantity(jfactor)
        self.primary_flux = PrimaryFlux(mass, channel=self.channel)
        super().__init__(scale=scale)

    def evaluate(self, energy, scale):
        """Evaluate dark matter decay model."""
        flux = (
            scale
            * self.jfactor
            * self.primary_flux(energy=energy * (1 + self.z))
            / self.LIFETIME_AGE_OF_UNIVERSE
            / self.mass
            / (4 * np.pi)
        )
        return flux

    def to_dict(self, full_output=False):
        data = super().to_dict(full_output=full_output)
        data["spectral"]["channel"] = self.channel
        data["spectral"]["mass"] = self.mass.to_string()
        data["spectral"]["jfactor"] = self.jfactor.to_string()
        data["spectral"]["z"] = self.z
        return data

    @classmethod
    def from_dict(cls, data):
        """Create spectral model from dictionary.

        Parameters
        ----------
        data : dict
            Dictionary with model data.

        Returns
        -------
        model : `DarkMatterDecaySpectralModel`
            Dark matter decay spectral model.
        """
        data = data["spectral"]
        data.pop("type")
        parameters = data.pop("parameters")
        scale = [p["value"] for p in parameters if p["name"] == "scale"][0]
        return cls(scale=scale, **data)
