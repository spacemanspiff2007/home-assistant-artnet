# home-assistant-artnet
Artnet integration for home-assistant

### Usage
Download [artnet.py](https://github.com/spacemanspiff2007/home-assistant-artnet/blob/master/artnet.py) and put it in the *'custom_components/light'* directory.
If there is no *'custom_components'* folder next to your *configuration.yaml* just create it with a subfolder *'light'*.

### Configuration
```yaml
- platform: artnet
  host: IP                              # IP of Art-Net Node
  max_fps: 25                           # Max 25 packages to ArtNet Node per second
  refresh_every: 120                    # Resend values if no fades are running every x seconds, 0 disables automatic refresh
  universes:                            # Support for multiple universes
    0:                                  # Nr of Universe (see configuration of your Art-Net Node)
        output_correction: quadratic    # optional: output correction for the whole universe, will be used as default if nothing is set for the channel
        devices:
        # Dimmer
        - channel: 128                  # first channel of dmx dimmer
          name: my_dimmer               # name
          type: dimmer                  # type
          transition: 1                 # default duration of fades in sec
          output_correction: quadratic  # optional: quadratic, cubic or quadruple. Applys different dimming curves to the output. Default is None which means linear dimming
        # RGB
        - channel: 129
          name: my_rgb_lamp
          type: rgb
          transition: 1
        # RGBW
        - channel: 132
          name: my_rgbw_lamp
          type: rgbw
          transition: 1
```
