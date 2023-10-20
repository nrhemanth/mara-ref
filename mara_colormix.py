#Imports
from opentrons import protocol_api
from opentrons.types import Location, Point

##Need to write the metadata which is the info about the protocol, who wrote it, what version was it written in etc...
metadata = {
    #'apiLevel': '2.15', ##API version 
    'protocolName': 'Moving Water', #Protocol name
    'description': '''This protocol is the outcome of following the
                   Python Protocol API, reference:
                   https://support.opentrons.com/s/article/Understanding-the-X-Y-Z-coordinates-of-the-OT-2 It takes a
                   transfer water to two lotation.''',
    'author': 'Clara'
    }

##Recommended to have a "Requirements" section
requirements = {"robotType": "OT-2", "apiLevel": "2.14"} ##Note: If putting 'apilevel' here, remove it from the metadata
