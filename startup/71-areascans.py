
import bluesky as bs
import bluesky.plans as bp
import bluesky.plan_stubs as bps
import numpy
import os
import matplotlib.pyplot as plt

from bluesky.preprocessors import subs_decorator
## see 65-derivedplot.py for DerivedPlot class
## see 10-motors.py and 20-dcm.py for motor definitions

run_report(__file__)


def areascan(slow, startslow, stopslow, nslow,
             fast, startfast, stopfast, nfast,
             detector, pluck=True):
    '''
    Generic areascan plan.  This is a RELATIVE scan, relative to the
    current positions of the selected motors.

    For example:
       RE(areascan('x', -1, 1, 21, 'y', -0.5, 0.5, 11, 'it'))

       slow:     motor or nickname of the slow axis
       sl1:      starting value for slow axis of a relative scan
       sl2:      ending value for slow axis of a relative scan
       nsl:      number of steps in slow axis
       fast:     motor or nickname of the fast axis
       fa1:      starting value for fast axis of a relative scan
       fa2:      ending value for fast axis of a relative scan
       nfa:      number of steps in fast axis
       detector: detector to display -- if, it, ir, or i0
       pluck:    flag for whether to offer to pluck & move motor

    slow and fast are either the BlueSky name for a motor (e.g. xafs_linx)
    or a nickname for an XAFS sample motor (e.g. 'x' for xafs_linx).

    This does not write an ASCII data file, but it does make a log entry.

    Use the as2dat() function to extract the areascan from the
    database and write it to a file.
    '''


    RE.msg_hook = None

    ## sanity checks on slow axis
    if type(slow) is str: slow = slow.lower()
    if slow not in motor_nicknames.keys() and 'EpicsMotor' not in str(type(slow)) and 'PseudoSingle' not in str(type(slow)):
        print(colored('\n*** %s is not a linescan motor (%s)\n' %
                      (slow, str.join(', ', motor_nicknames.keys())), 'lightred'))
        yield from null()
        return
    if slow in motor_nicknames.keys():
        slow = motor_nicknames[slow]

    ## sanity checks on fast axis
    if type(fast) is str: fast = fast.lower()
    if fast not in motor_nicknames.keys() and 'EpicsMotor' not in str(type(fast)) and 'PseudoSingle' not in str(type(fast)):
        print(colored('\n*** %s is not a linescan motor (%s)\n' %
                      (fast, str.join(', ', motor_nicknames.keys())), 'lightred'))
        yield from null()
        return
    if fast in motor_nicknames.keys():
        fast = motor_nicknames[fast]

    detector = detector.capitalize()
    yield from abs_set(_locked_dwell_time, 0.1)
    dets = [quadem1]
    if detector == 'If':
        dets = dets.append(vor)
        detector = 'ROI1'

    if 'PseudoSingle' in str(type(slow)):
        valueslow = slow.readback.value
    else:
        valueslow = slow.user_readback.value
    line1 = 'slow motor: %s, %.3f, %.3f, %d -- starting at %.3f\n' % \
            (slow.name, startslow, stopslow, nslow, valueslow)

    if 'PseudoSingle' in str(type(fast)):
        valuefast = fast.readback.value
    else:
        valuefast = fast.user_readback.value
    line2 = 'fast motor: %s, %.3f, %.3f, %d -- starting at %.3f\n' % \
            (fast.name, startfast, stopfast, nfast, valuefast)

    extent = (valuefast + startfast, valuefast + stopfast,
              valueslow + startslow, valueslow + stopslow)

    areaplot = LiveGrid((nslow, nfast), detector, aspect='equal', extent=extent,
                        xlabel='fast motor: %s' % fast.name,
                        ylabel='slow motor: %s' % slow.name)
    BMM_cpl.ax     = areaplot.ax
    BMM_cpl.fig    = areaplot.ax.figure
    BMM_cpl.motor  = fast
    BMM_cpl.motor2 = slow
    BMM_cpl.fig.canvas.mpl_connect('close_event', handle_close)

    @subs_decorator(areaplot)
    def make_areascan():
        yield from rel_grid_scan(dets,
                                 slow, startslow, stopslow, nslow,
                                 fast, startfast, stopfast, nfast,
                                 False, md={'slow_motor': slow.name, 'fast_motor': fast.name})
    yield from make_areascan()
    BMM_log_info('areascan observing: %s\n%s%s\tuid = %s, scan_id = %d' %
                 (detector, line1, line2, db[-1].start['uid'], db[-1].start['scan_id']))

    yield from abs_set(_locked_dwell_time, 0.5)
    RE.msg_hook = BMM_msg_hook
    if pluck is True:
        action = input('\n' + colored('Pluck motor position from the plot? [Y/n then enter] ', 'white'))
        if action.lower() == 'n' or action.lower() == 'q':
            return(yield from null())
        print('Single click the left mouse button on the plot to pluck a point...')
        cid = BMM_cpl.fig.canvas.mpl_connect('button_press_event', interpret_click) # see 65-derivedplot.py and
        while BMM_cpl.x is None:                            #  https://matplotlib.org/users/event_handling.html
            yield from sleep(0.5)
        yield from mv(fast, BMM_cpl.x, slow, BMM_cpl.y)
        cid = BMM_cpl.fig.canvas.mpl_disconnect(cid)
        BMM_cpl.x = BMM_cpl.y = None


def as2dat(datafile, key):
    '''
    Export an areascan database entry to a simple column data file.

      as2dat('/path/to/myfile.dat', 2948)

    or

      as2dat('/path/to/myfile.dat', '42447313-46a5-42ef-bf8a-46fedc2c2bd1')

    The arguments are a data file name and the database key.
    '''

    if os.path.isfile(datafile):
        print(colored('%s already exists!  Bailing out....' % datafile, 'lightred'))
        return
    dataframe = db[key]
    if 'slow_motor' not in dataframe['start']:
        print(colored('That database entry does not seem to be a an areascan (missing slow_motor)', 'lightred'))
        return
    if 'fast_motor' not in dataframe['start']:
        print(colored('That database entry does not seem to be a an areascan (missing fast_motor)', 'lightred'))
        return

    devices = dataframe.devices() # note: this is a _set_ (this is helpful: https://snakify.org/en/lessons/sets/)

    if 'vor' in devices:
        abscissa = list(devices - {'quadem1', 'vor'})
        column_list = [dataframe['start']['slow_motor'], dataframe['start']['fast_motor'],
                       'I0', 'It', 'Ir',
                       'DTC1', 'DTC2', 'DTC3', 'DTC4',
                       'ROI1', 'ICR1', 'OCR1',
                       'ROI2', 'ICR2', 'OCR2',
                       'ROI3', 'ICR3', 'OCR3',
                       'ROI4', 'ICR4', 'OCR4']
        template = "  %.3f  %.3f  %.6f  %.6f  %.6f  %.6f  %.6f  %.6f  %.6f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f\n"
    else:
        abscissa = list(devices - {'quadem1',})
        template = "  %.3f  %.3f  %.6f  %.6f  %.6f\n"
        column_list = [dataframe['start']['slow_motor'], dataframe['start']['fast_motor'],
                       'I0', 'It', 'Ir']

    table = dataframe.table()
    this = table.loc[:,column_list]

    handle = open(datafile, 'w')
    handle.write('# Scan.uid: %s\n' % dataframe['start']['uid'])
    handle.write('# Scan.transient_id: %d\n' % dataframe['start']['scan_id'])
    handle.write('# ==========================================================\n')
    handle.write('# ' + '  '.join(column_list) + '\n')
    slowval = None
    for i in range(0,len(this)):
        if i>0 and this.iloc[i,0] != slowval:
            handle.write('\n')
        handle.write(template % tuple(this.iloc[i]))
        slowval = this.iloc[i,0]
    handle.flush()
    handle.close()
    print(colored('wrote areascan to %s' % datafile, 'white'))