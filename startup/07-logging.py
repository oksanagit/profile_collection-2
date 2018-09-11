import logging
from os import chmod

run_report(__file__)

BMM_logger          = logging.getLogger('BMM_logger')
BMM_logger.handlers = []

BMM_formatter       = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s\n%(message)s')
BMM_log_master_file = '/home/xf06bm/Data/BMM_master.log'
if os.path.isfile(BMM_log_master_file):
    chmod(BMM_log_master_file, 0o644)
BMM_log_master      = logging.FileHandler(BMM_log_master_file)
BMM_log_master.setFormatter(BMM_formatter)
BMM_logger.addHandler(BMM_log_master)
BMM_logger.setLevel(logging.INFO)
chmod(BMM_log_master_file, 0o444)

BMM_log_user = None

## this is intended to be a log file in the experiment folder
## thus all scans, etc. relevant to the experiment will be logged with the data
## call this at the beginning of the beamtime
def BMM_user_log(filename):
    BMM_log_user = logging.FileHandler(filename)
    BMM_log_user.setFormatter(BMM_formatter)
    BMM_logger.addHandler(BMM_log_user)

## remove all but the master log from the list of handlers
def BMM_unset_user_log():
    BMM_logger.handlers = []
    BMM_logger.addHandler(BMM_log_master)

## use this command to properly format the log message, manage file permissions, etc
def BMM_log_info(message):
    chmod(BMM_log_master_file, 0o644)
    entry = ''
    for line in message.split('\n'):
        entry += '    ' + line + '\n'
    BMM_logger.info(entry)
    chmod(BMM_log_master_file, 0o444)




######################################################################################
# here is an example of what a message tuple looks like when moving a motor          #
# (each item in the tuple is on it's own line):                                      #
#     set:                                                                           #
#     (XAFSEpicsMotor(prefix='XF:06BMA-BI{XAFS-Ax:LinX}Mtr', name='xafs_linx', ... ) #
#     (-91.5999475,),                                                                #
#     {'group': '8c8df020-23aa-451e-b411-c427bc80b375'}                              #
######################################################################################
def BMM_msg_hook(msg):
    if msg[0] == 'set':
        if 'EpicsMotor' in str(type(msg[1])):
            print('Moving %s to %.3f' % (msg[1].name, msg[2][0]))
            BMM_log_info('Moving %s to %.3f' % (msg[1].name, msg[2][0]))
        elif 'EpicsSignal' in str(type(msg[1])):
            print('Setting %s to %.3f' % (msg[1].name, msg[2][0]))
            BMM_log_info('Setting %s to %.3f' % (msg[1].name, msg[2][0]))

RE.msg_hook = BMM_msg_hook
