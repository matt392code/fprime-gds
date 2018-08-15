'''
@brief Main frame factory class

This class demonstrated how to set up a pipeline with the GDS API and provides
an interface for creating additional GDS windows that use this pipeline

@data Created July 18, 2018
@author Josef Biberstein

@bug No known bugs
'''

from loaders import ch_py_loader, ch_xml_loader
from loaders import event_py_loader, event_xml_loader
from loaders import pkt_xml_loader
from loaders import cmd_py_loader, cmd_xml_loader

from decoders import ch_decoder
from decoders import event_decoder
from decoders import pkt_decoder
from encoders import cmd_encoder

from distributor import distributor

from client_socket import client_socket

from gui import GDSMainFrameImpl

from logger import DataLogger

import os
import datetime

# TODO document all methods
class MainFrameFactory(object):
    '''Factory that creates new windows for the GDS'''

    def __init__(self, opts, config):
        """Constructor for the Main panel factory

        Arguments:
            opts {options object} -- The options passed to the startup script (gds.py)
            config {ConfigManager object} -- The config object for the program
        """

        self.config = config

        self.opts = opts

        self.client_socket = None
        self.dist = None

        self.evnt_ldr = None
        self.cmd_ldr = None
        self.ch_ldr = None
        self.pkt_ldr = None

        self.cmd_enc = None
        self.event_dec = None
        self.ch_dec = None
        self.pkt_dec = None

        self.cmd_name_dict = None

        self.main_frame_instances = []
        
        self.ch_dict = None

        self.logger = None

        # Setup log file location
        self.log_dir = os.path.dirname(os.path.realpath(__file__)) + '/../logs/' + str(datetime.date.today()) + os.sep
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def create_new_window(self):
        """Create a new instance of the GDS window

        Raises:
            Exception -- raised if the setup_pipline() method wasn't called before this method
        """

        if len(self.main_frame_instances) > 0:
            frame = GDSMainFrameImpl.MainFrameImpl(None, self, \
                evnt_pnl_state=self.main_frame_instances[0].event_pnl.getEventLogState(), \
                tlm_pnl_state=self.main_frame_instances[0].telem_pnl.getChannelTelemDataViewState(), \
                status_bar_state=self.main_frame_instances[0].status_bar.get_state(), ch_dict=self.ch_dict, config=self.config)

            self.register_all(frame)

            self.main_frame_instances.append(frame)
            frame.Show(True)
        else:
            raise Exception("Please run setup_pipline() before using this method to create another window")


    def setup_pipeline(self):
        """Setup the pipline of data from the client to the GUI. Creates one instance of main GDS window for you.

        Raises:
            Exception -- raised if no dictionary path passed in the opts object
        """

        # TODO comment this function to explain

        self.dist = distributor.Distributor(self.config)
        self.client_socket = client_socket.ThreadedTCPSocketClient()

        # Choose the dictionary type we will use
        if self.opts.generated_path != None:
            use_py_dicts = True
        elif self.opts.xml_dict_path != None:
            use_py_dicts = False
        else:
            raise Exception("No Dictionary path passed in options")

        if use_py_dicts:
            self.evnt_ldr = event_py_loader.EventPyLoader()
            eid_dict = self.evnt_ldr.get_id_dict(self.opts.generated_path + os.sep + "events")

            self.cmd_ldr = cmd_py_loader.CmdPyLoader()
            self.cmd_name_dict = self.cmd_ldr.get_name_dict(self.opts.generated_path + os.sep + "commands")

            self.ch_ldr = ch_py_loader.ChPyLoader()
            ch_dict = self.ch_ldr.get_id_dict(self.opts.generated_path + os.sep + "channels")
            ch_name_dict = self.ch_ldr.get_name_dict(self.opts.generated_path + os.sep + "channels")
        else:
            self.evnt_ldr = event_xml_loader.EventXmlLoader()
            eid_dict = self.evnt_ldr.get_id_dict(self.opts.xml_dict_path)

            self.cmd_ldr = cmd_xml_loader.CmdXmlLoader()
            self.cmd_name_dict = self.cmd_ldr.get_name_dict(self.opts.xml_dict_path)

            self.ch_ldr = ch_xml_loader.ChXmlLoader()
            ch_dict = self.ch_ldr.get_id_dict(self.opts.xml_dict_path)
            ch_name_dict = self.ch_ldr.get_name_dict(self.opts.xml_dict_path)

        self.ch_dict = ch_dict
        self.cmd_enc = cmd_encoder.CmdEncoder()
        self.event_dec = event_decoder.EventDecoder(eid_dict)
        self.ch_dec = ch_decoder.ChDecoder(ch_dict)

        self.client_socket.register_distributor(self.dist)

        self.cmd_enc.register(self.client_socket)

        self.dist.register("FW_PACKET_LOG", self.event_dec)
        self.dist.register("FW_PACKET_TELEM", self.ch_dec)

        # TODO find a cleaner way to handle implementations without a packet spec
        if (self.opts.pkt_spec_path != None):
            self.pkt_ldr = pkt_xml_loader.PktXmlLoader()
            pkt_dict = self.pkt_ldr.get_id_dict(self.opts.pkt_spec_path, ch_name_dict)
            self.pkt_dec = pkt_decoder.PktDecoder(pkt_dict, ch_dict)
            self.dist.register("FW_PACKET_PACKETIZED_TLM", self.pkt_dec)

        frame = GDSMainFrameImpl.MainFrameImpl(None, self, ch_dict=ch_dict, config=self.config)

        self.register_all(frame)

        frame.Show(True)
        self.main_frame_instances.append(frame)

        # Setup the logging pipeline
        self.logger = DataLogger.DataLogger(self.log_dir, verbose=True, csv=True)
        self.event_dec.register(self.logger)
        self.ch_dec.register(self.logger)
        self.client_socket.register_distributor(self.logger)
        self.cmd_enc.register(self.logger)

    def register_all(self, frame):
        '''
        Register all decoders, encoders and panels

        Args:
            frame (MainFrameImpl): Main frame implementation object with panels
                                   to register
        '''
        self.event_dec.register(frame.event_pnl)
        self.ch_dec.register(frame.telem_pnl)

        if (self.opts.pkt_spec_path != None):
            self.pkt_dec.register(frame.telem_pnl)

        # Register the status panel so that it can dump ray data to the consol
        self.client_socket.register_distributor(frame.status_pnl)
        self.cmd_enc.register(frame.status_pnl)

        frame.cmd_pnl.register_encoder(self.cmd_enc)

        self.client_socket.register_distributor(frame)
        self.cmd_enc.register(frame)

