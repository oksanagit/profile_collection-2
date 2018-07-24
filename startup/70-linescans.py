import bluesky as bs
import bluesky.plans as bp
import bluesky.plan_stubs as bps
import numpy
import os

from bluesky.preprocessors import subs_decorator
## see 88-plot-hacking.py for definitions of plot functions for DerivedPlot
## see 10-motors.py and 20-dcm.py for motor definitions

run_report(__file__)

def slit_height(start=-3.0, stop=3.0, nsteps=61):
    '''
    Perform a relative scan of the DM# BCT motor around the current
    position to find the optimal position for slits3.  No further
    analysis of the scan is done -- YOU must move to the optimal position.
    '''
    motor = dm3_bct
    func = lambda doc: (doc['data'][motor.name], doc['data']['I0'])
    plot = DerivedPlot(func, xlabel=motor.name, ylabel='I0')

    BMM_log_info('slit height scan: %s, %s, %.3f, %.3f, %d -- starting at %.3f'
                 % (motor.name, 'i0', start, stop, nsteps, motor.user_readback.value))

    @subs_decorator(plot)
    def scan_slit():
        yield from abs_set(quadem1.averaging_time, 0.1)
        yield from abs_set(motor.kill_cmd, 1)

        yield from rel_scan([quadem1], motor, start, stop, nsteps)

        yield from bps.sleep(3.0)
        yield from abs_set(quadem1.averaging_time, 0.5)
        yield from abs_set(motor.kill_cmd, 1)

    yield from scan_slit()
    BMM_log_info('slit height scan finished, uid = %s, scan_id = %d' %
                 (db[-1].start['uid'], db[-1].start['scan_id']))


def rocking_curve(start=-0.10, stop=0.10, nsteps=101):
    '''
    Perform a relative scan of the DCM 2nd crystal pitch around the current
    position to find the peak of the crystal rocking curve.  At the end, move
    to the position of maximum intensity on I0.
    '''
    motor = dcm_pitch
    func = lambda doc: (doc['data'][motor.name], doc['data']['I0'])
    plot = DerivedPlot(func, xlabel=motor.name, ylabel='I0')

    BMM_log_info('rocking curve scan: %s, %s, %.3f, %.3f, %d -- starting at %.3f'
                 % (motor.name, 'i0', start, stop, nsteps, motor.user_readback.value))

    @subs_decorator(plot)
    def scan_dcmpitch():
        yield from abs_set(quadem1.averaging_time, 0.1)
        yield from abs_set(motor.kill_cmd, 1)

        yield from rel_scan([quadem1], motor, start, stop, nsteps)

        t  = db[-1].table()
        maxval = t['I0'].max()
        top = float(t[t['I0'] == maxval]['dcm_pitch']) # position of max intensity
        ## see https://pandas.pydata.org/pandas-docs/stable/10min.html#boolean-indexing

        yield from bps.sleep(3.0)
        yield from abs_set(quadem1.averaging_time, 0.5)
        yield from abs_set(motor.kill_cmd, 1)

        yield from mv(motor, top)
        yield from bps.sleep(3.0)
        yield from abs_set(motor.kill_cmd, 1)

    yield from scan_dcmpitch()
    BMM_log_info('rocking curve scan finished, uid = %s, scan_id = %d' %
                 (db[-1].start['uid'], db[-1].start['scan_id']))



####################################
# generic linescan vs. It/If/Ir/I0 #
####################################
def linescan(axis, detector, start, stop, nsteps): # inegration time?
    '''
    Generic linescan plan.  This is a RELATIVE scan, relative to the
    current position of the selected motor.

    For example:
       RE(linescan('x', 'it', -1, 1, 21))

       axis :    motor or nickname
       detector: detector to display -- if, it, ir, or i0
       start:    starting value for a relative scan
       stop:     ending value for a relative scan
       nsteps:   number of steps in scan

    The motor is either the BlueSky name for a motor (e.g. xafs_linx)
    or a nickname for an XAFS sample motor (e.g. 'x' for xafs_linx).

    This does not write an ASCII data file, but it does make a log entry.

    Use the ls2dat() function to extract the linescan from the
    database and write it to a file.
    '''

    ##        linear stages        tilt stage           rotation stages
    motors = {'x'    : xafs_linx,  'roll' : xafs_roll,  'rh' : xafs_roth,
              'y'    : xafs_liny,  'pitch': xafs_pitch, 'rb' : xafs_rotb,
              's'    : xafs_lins,  'p'    : xafs_pitch, 'rs' : xafs_rots,
              'xs'   : xafs_linxs, 'r'    : xafs_roll,
          }

    ## sanitize input and set thismotor to an actual motor
    if type(axis) is str: axis = axis.lower()
    detector = detector.capitalize()

    ## sanity checks on axis
    if axis not in motors.keys() and 'EpicsMotor' not in str(type(axis)) and 'PseudoSingle' not in str(type(axis)):
        print(colored('\n*** %s is not a linescan motor (%s)\n' %
                      (axis, str.join(', ', motors.keys())), color='red'))
        yield from null()
        return

    if 'EpicsMotor' in str(type(axis)):
        thismotor = axis
    elif 'PseudoSingle' in str(type(axis)):
        thismotor = axis
    else:                       # presume it's an xafs_XXXX motor
        thismotor = motors[axis]

    ## sanity checks on detector
    if detector not in ('It', 'If', 'I0'):
        print(colored('\n*** %s is not a linescan measurement (%s)\n' %
                      (detector, 'it, if'), color='red'))
        yield from null()
        return

    yield from abs_set(_locked_dwell_time, 0.1)
    dets  = [quadem1,]
    denominator = ''

    ## func is an anonymous function, built on the fly, for feeding to DerivedPlot
    if detector == 'It':
        denominator = ' / I0'
        func = lambda doc: (doc['data'][thismotor.name], doc['data']['It']/doc['data']['I0'])
    elif detector == 'Ir':
        denominator = ' / It'
        func = lambda doc: (doc['data'][thismotor.name], doc['data']['Ir']/doc['data']['It'])
    elif detector == 'I0':
        func = lambda doc: (doc['data'][thismotor.name], doc['data']['I0'])
    elif detector == 'If':
        dets.append(vor)
        denominator = ' / I0'
        func = lambda doc: (doc['data'][thismotor.name],
                            (doc['data']['DTC1'] +
                             doc['data']['DTC2'] +
                             doc['data']['DTC3'] +
                             doc['data']['DTC4']   ) / doc['data']['I0'])
    ## and this is the appropriate way to plot this linescan
    plot = DerivedPlot(func,
                       xlabel=thismotor.name,
                       ylabel=detector+denominator)

    if 'PseudoSingle' in str(type(axis)):
        BMM_log_info('linescan: %s, %s, %.3f, %.3f, %d -- starting at %.3f' %
                     (thismotor.name, detector, start, stop, nsteps, thismotor.readback.value))
    else:
        BMM_log_info('linescan: %s, %s, %.3f, %.3f, %d -- starting at %.3f' %
                     (thismotor.name, detector, start, stop, nsteps, thismotor.user_readback.value))

    @subs_decorator(plot)
    def scan_xafs_motor(dets, motor, start, stop, nsteps):
        yield from rel_scan(dets, motor, start, stop, nsteps)

    yield from scan_xafs_motor(dets, thismotor, start, stop, nsteps)
    BMM_log_info('linescan finished, uid = %s, scan_id = %d' %
                 (db[-1].start['uid'], db[-1].start['scan_id']))

    yield from abs_set(_locked_dwell_time, 0.5)

    # if axis == 'x':
    #     motor = xafs_linx
    #     if detector == 'it':
    #         plot  = DerivedPlot(xscan, xlabel='sample X', ylabel='It / I0')
    #     elif detector == 'if':
    #         plot  = DerivedPlot(dt_x,  xlabel='sample X', ylabel='If / I0')
    #         dets.append(vor)

    # elif axis == 'q':
    #     dets  = [quadem1,]
    #     motor = xafs_liny
    #     #text  = 'def qscan(doc): return (doc[\'data\'][\'xafs_liny\'], doc[\'data\'][\'It\'])'
    #     #func = eval(text)
    #     func = lambda doc: (doc['data']['xafs_liny'], doc['data']['It'])
    #     plot  = DerivedPlot(func, xlabel='sample Q', ylabel='It')


    # elif axis == 'y':
    #     motor = xafs_liny
    #     dets  = [quadem1,]
    #     if detector == 'it':
    #         plot  = DerivedPlot(yscan, xlabel='sample X', ylabel='It / I0')
    #     elif detector == 'if':
    #         plot  = DerivedPlot(dt_y,  xlabel='sample X', ylabel='If / I0')
    #         dets.append(vor)

    # elif axis == 'roll':
    #     motor = xafs_roll
    #     dets  = [quadem1,]
    #     if detector == 'it':
    #         plot  = DerivedPlot(rollscan_trans, xlabel='sample roll', ylabel='It / I0')
    #     elif detector == 'if':
    #         plot  = DerivedPlot(rollscan_fluo,  xlabel='sample roll', ylabel='If / I0')
    #         dets.append(vor)

    # elif axis == 'pitch':
    #     motor = xafs_pitch
    #     dets  = [quadem1,]
    #     if detector == 'it':
    #         plot  = DerivedPlot(pitchscan_trans, xlabel='sample roll', ylabel='It / I0')
    #     elif detector == 'if':
    #         plot  = DerivedPlot(pitchscan_fluo,  xlabel='sample roll', ylabel='If / I0')
    #         dets.append(vor)



#############################################################
# extract a linescan from the database, write an ascii file #
#############################################################
def ls2dat(datafile, key):
    '''
    Export a linescan database entry to a simple column data file.

      ls2dat('/path/to/myfile.dat', 1533)

    or

      ls2dat('/path/to/myfile.dat', '0783ac3a-658b-44b0-bba5-ed4e0c4e7216')

    The arguments are a data file name and the database key.
    '''
    if os.path.isfile(datafile):
        print(colored('%s already exists!  Bailing out....' % datafile, color='red'))
        return
    handle = open(datafile, 'w')
    dataframe = db[key]
    devices = dataframe.devices() # note: this is a _set_ (this is helpful: https://snakify.org/en/lessons/sets/)
    if 'vor' in devices:
        abscissa = (devices - {'quadem1', 'vor'}).pop()
        column_list = [abscissa, 'I0', 'It', 'Ir',
                       'DTC1', 'DTC2', 'DTC3', 'DTC4',
                       'ROI1', 'ICR1', 'OCR1',
                       'ROI2', 'ICR2', 'OCR2',
                       'ROI3', 'ICR3', 'OCR3',
                       'ROI4', 'ICR4', 'OCR4']
        template = "  %.3f  %.6f  %.6f  %.6f  %.6f  %.6f  %.6f  %.6f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f  %.1f\n"
    else:
        abscissa = (devices - {'quadem1',}).pop()
        template = "  %.3f  %.6f  %.6f  %.6f\n"
        column_list = [abscissa, 'I0', 'It', 'Ir']

    table = dataframe.table()
    this = table.loc[:,column_list]

    handle.write('# ' + '  '.join(column_list) + '\n')
    for i in range(0,len(this)):
        handle.write(template % tuple(this.iloc[i]))
    handle.flush()
    handle.close()
    print(colored('wrote %s' % datafile, color='white'))


def center_sample_y():
    yield from linescan(xafs_liny, 'it', -1.5, 1.5, 61)
    table = db[-1].table()
    diff = -1 * table['It'].diff()
    inflection = table['xafs_liny'][diff.idxmax()]
    yield from mv(xafs_liny, inflection)
    print(colored('Optimal position in y at %.3f' % inflection, color='white'))

def center_sample_roll():
    yield from linescan(xafs_roll, 'it', -3, 3, 61)
    table = db[-1].table()
    peak = table['xafs_roll'][table['It'].idxmax()]
    yield from mv(xafs_roll, peak)
    print(colored('Optimal position in roll at %.3f' % peak, color='white'))

def align_flat_sample(angle=2):
    yield from center_sample_y()
    yield from center_sample_roll()
    yield from center_sample_y()
    yield from center_sample_roll()
    yield from mv(xafs_roll, angle)