import time
import typing

from homeassistant.components import light
from homeassistant.const import CONF_DEVICES
from homeassistant.const import CONF_FRIENDLY_NAME as CONF_DEVICE_FRIENDLY_NAME
from homeassistant.const import CONF_HOST as CONF_NODE_HOST
from homeassistant.const import CONF_NAME          as CONF_DEVICE_NAME
from homeassistant.const import CONF_PORT as CONF_NODE_PORT
from homeassistant.const import CONF_TYPE          as CONF_DEVICE_TYPE

CONF_DEVICE_TRANSITION = light.ATTR_TRANSITION

import homeassistant.helpers.config_validation as cv
import homeassistant.util.color as color_util
import voluptuous as vol

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

REQUIREMENTS = [ 'pyartnet==0.5.0']

log.info( f'PyArtNet: {REQUIREMENTS[0]}')
log.info( f'Version : 2018.10.18 - 16:22')

CONF_NODE_MAX_FPS = 'max_fps'
CONF_NODE_REFRESH = 'refresh_every'
CONF_NODE_UNIVERSES = 'universes'

CONF_DEVICE_CHANNEL    = 'channel'
CONF_OUTPUT_CORRECTION = 'output_correction'



AVAILABLE_CORRECTIONS = { 'linear' : None, 'quadratic' : None, 'cubic' : None, 'quadruple' : None}


# Import with syntax highlighting
pyartnet = None
if typing.TYPE_CHECKING:
    import pyartnet

ARTNET_NODES = {}
async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    global pyartnet
    if pyartnet is None:
        import pyartnet
        AVAILABLE_CORRECTIONS['quadratic'] = pyartnet.output_correction.quadratic
        AVAILABLE_CORRECTIONS['cubic']     = pyartnet.output_correction.cubic
        AVAILABLE_CORRECTIONS['quadruple'] = pyartnet.output_correction.quadruple
    
    
    import pprint
    for l in pprint.pformat(config).splitlines():
        log.info(l)
    
    host = config.get(CONF_NODE_HOST)
    port = config.get(CONF_NODE_PORT)

    #setup Node
    __id = f'{host}:{port}'
    if not __id in ARTNET_NODES:
        __node = pyartnet.ArtNetNode(host, port, max_fps=config[CONF_NODE_MAX_FPS], refresh_every=config[CONF_NODE_REFRESH])
        __node.start()
        ARTNET_NODES[id] = __node
    node = ARTNET_NODES[id]
    assert isinstance(node, pyartnet.ArtNetNode), type(node)
   
    device_list = []
    for universe_nr, universe_cfg in config[CONF_NODE_UNIVERSES].items():
        try:
            universe = node.get_universe(universe_nr)
        except KeyError:
            universe = node.add_universe(universe_nr)
            universe.output_correction = AVAILABLE_CORRECTIONS.get(universe_cfg[CONF_OUTPUT_CORRECTION])
            
        for device in universe_cfg[CONF_DEVICES]:   # type: dict
            device = device.copy()
            cls = __CLASS_TYPE[device[CONF_DEVICE_TYPE]]
            device.pop(CONF_DEVICE_TYPE)
            
            # create device
            d = cls(**device)   # type: ArtnetBaseLight
            d.set_channel( universe.add_channel(device[CONF_DEVICE_CHANNEL], d.CHANNEL_WIDTH, d._name))
            d._channel.output_correction = AVAILABLE_CORRECTIONS.get(device[CONF_OUTPUT_CORRECTION])
            
            device_list.append(d)

    async_add_devices(device_list)
    return True


class ArtnetBaseLight(light.Light):
    def __init__(self, name, **kwargs):
        self._name = name

        self._brightness = 255
        self._fade_time  = kwargs[CONF_DEVICE_TRANSITION]
        self._state = False

        # channel & notification callbacks
        self._channel : pyartnet.DmxChannel = None
        self._channel_last_update = 0

    def set_channel(self, channel):
        "Set the channel & the callbacks"
        assert isinstance(channel, pyartnet.DmxChannel)
        self._channel = channel
        self._channel.callback_value_changed = self._channel_value_change
        self._channel.callback_fade_finished = self._channel_fade_finish

    
    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._brightness

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._features

    @property
    def device_state_attributes(self):
        data = {}
        data['dmx_channels'] = [k for k in range(self._channel.start, self._channel.start + self._channel.width, 1)]
        data['dmx_values']   = self._channel.get_channel_values()
        data[CONF_DEVICE_TRANSITION] = self._fade_time
        self._channel_last_update = time.time()
        return data

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state
    
    @property
    def force_update(self):
        return True

    @property
    def should_poll(self):
        return False

    @property
    def fade_time(self):
        return self._fade_time

    @fade_time.setter
    def fade_time(self, value):
        self._fade_time = value

    def _channel_value_change(self):
        "Shedule update while fade is running"
        if time.time() - self._channel_last_update > 1.1:
            self._channel_last_update = time.time()
            self.async_schedule_update_ha_state()
    
    def _channel_fade_finish(self):
        "Fade is finished -> shedule update"
        self._channel_last_update = time.time()
        self.async_schedule_update_ha_state()

    def get_target_values(self) -> list:
        "Return the Target DMX Values"
        raise NotImplementedError()

    async def async_create_fade(self, **kwargs):
        "Instruct the light to turn on"
        self._state = True
        
        transition =  kwargs.get(light.ATTR_TRANSITION, self._fade_time)
        
        self._channel.add_fade(self.get_target_values(), transition * 1000, pyartnet.fades.LinearFade)

        self.async_schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        """
        Instruct the light to turn off. If a transition time has been specified in seconds
        the controller will fade.
        """
        transition = kwargs.get(light.ATTR_TRANSITION, self._fade_time)

        logging.debug("Turning off '%s' with transition  %i", self._name, transition)
        self._channel.add_fade([0 for k in range(self._channel.width)], transition * 1000, pyartnet.fades.LinearFade)

        self._state = False
        self.async_schedule_update_ha_state()


class ArtnetDimmer(ArtnetBaseLight):
    CONF_TYPE = 'dimmer'
    CHANNEL_WIDTH = 1
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self._features = (light.SUPPORT_BRIGHTNESS | light.SUPPORT_TRANSITION)

    def get_target_values(self):
        return [self.brightness]

    async def async_turn_on(self, **kwargs):
        
        # Update state from service call
        if light.ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[light.ATTR_BRIGHTNESS]

        await super().async_create_fade(**kwargs)


class ArtnetRGB(ArtnetBaseLight):
    CONF_TYPE = 'rgb'
    CHANNEL_WIDTH = 3
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self._features = (light.SUPPORT_BRIGHTNESS | light.SUPPORT_TRANSITION | light.SUPPORT_COLOR)
        self._rgb = [255, 255, 255]
        
        self._scale_factor = 1
    
    def get_target_values(self):
        l = [round(k * self._scale_factor) for k in self._rgb]
        return l
    
    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        # RGB already contains brightness information
        if light.ATTR_RGB_COLOR in kwargs:
            self._rgb = kwargs[light.ATTR_RGB_COLOR]
            self._brightness = max(self._rgb)
            self._scale_factor = 1
        
        if light.ATTR_HS_COLOR in kwargs:
            self._rgb = list(color_util.color_hs_to_RGB(*kwargs[light.ATTR_HS_COLOR]))
        
        if light.ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[light.ATTR_BRIGHTNESS]
            self._scale_factor = self._brightness / 255
      
        await super().async_create_fade(**kwargs)
        return None


class ArtnetRGBW(ArtnetRGB):
    CONF_TYPE = 'rgbw'
    CHANNEL_WIDTH = 4
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self._features = (light.SUPPORT_BRIGHTNESS | light.SUPPORT_TRANSITION | light.SUPPORT_COLOR| light.SUPPORT_WHITE_VALUE)
        self._white = 255
    
    def get_target_values(self):
        l = super().get_target_values()
        l.append(round(self._white * self._scale_factor))
        return l
    
    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        # RGB already contains brightness information
        if light.ATTR_WHITE_VALUE in kwargs:
            self._white = kwargs[light.ATTR_WHITE_VALUE]

        await super().async_turn_on(**kwargs)


#------------------------------------------------------------------------------
# conf
#------------------------------------------------------------------------------

__CLASS_LIST = [ArtnetDimmer, ArtnetRGB, ArtnetRGBW]
__CLASS_TYPE = {k.CONF_TYPE : k for k in __CLASS_LIST}

PLATFORM_SCHEMA = light.PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NODE_HOST): cv.string,
    vol.Required(CONF_NODE_UNIVERSES): {
        vol.All(int, vol.Range(min=0, max=1024)): {
            vol.Optional(CONF_OUTPUT_CORRECTION, default=None): vol.Any(None, vol.In(AVAILABLE_CORRECTIONS)),
            CONF_DEVICES: vol.All(cv.ensure_list, [
                {
                    vol.Required(CONF_DEVICE_CHANNEL): vol.All(vol.Coerce(int), vol.Range(min=1, max=512)),
                    vol.Required(CONF_DEVICE_NAME): cv.string,
                    vol.Optional(CONF_DEVICE_FRIENDLY_NAME): cv.string,
                    vol.Optional(CONF_DEVICE_TYPE): vol.In([k.CONF_TYPE for k in __CLASS_LIST]),
                    vol.Optional(CONF_DEVICE_TRANSITION, default=0): vol.All(vol.Coerce(float), vol.Range(min=0, max=999)),
                    vol.Optional(CONF_OUTPUT_CORRECTION, default=None): vol.Any(None, vol.In(AVAILABLE_CORRECTIONS)),
                }
            ])
        },
    },
    vol.Optional(CONF_NODE_PORT, default=6454): cv.port,
    vol.Optional(CONF_NODE_MAX_FPS, default=25): vol.All(vol.Coerce(int), vol.Range(min=1, max=40)),
    vol.Optional(CONF_NODE_REFRESH, default=120): vol.All(vol.Coerce(int), vol.Range(min=0, max=9999)),
    
}, required=True, extra=vol.PREVENT_EXTRA)
