from __future__ import annotations
from pyexpat import model
from typing import Any, Optional, Type, Callable, Iterable, Sequence, Tuple
from typing_extensions import Self
from abc import ABC, abstractmethod

import pyvisa


# Constants
# TODO: compare with the other tek instruments

VI_READ_TERMINATION = '\n'

VI_WRITE_TERMINATION = '\n'

VI_TIMEOUT = 2000

VI_OPEN_TIMEOUT = 0

VI_QUERY_DELAY = 0.001


# Classes

class Error(Exception):
    """Abstract basic exception class for this module."""


class InstrIOError(Error):
    """Exception class for Instr I/O errors."""

    def __init__(self, msg) -> None:
        self.msg = msg
        super(InstrIOError, self).__init__(msg)

    def __reduce__(self) -> Tuple[type, Tuple[int]]:
        """Store the error code when pickling."""
        return (InstrIOError, (self.msg,))


class BaseInstrument(ABC):
    """ABC of all the instrument model classes."""

    @property
    @abstractmethod
    def brand(self) -> str:
        """The brand/manufactory of the instrument."""

    @property
    @abstractmethod
    def model(self) -> str:
        """The model name of the instrument."""

    def __init__(self, resource_name: str):
        """
        Args:
            resource_name: The instrument resource name. Please refer to 
                `resource_name` property for more information.
        """
        self.__resource_name = resource_name
        super(BaseInstrument, self).__init__()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__!r}({self.resource_name!r})>"

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @abstractmethod
    def close(self) -> None:
        """Release the instrument resource."""

    @property
    def resource_name(self) -> str:
        """
        - For VISA compatible instruments, it is the resource name or alias of 
        the VISA resource.
        """
        return self.__resource_name
    
    @abstractmethod
    def _check_communication(self) -> None:
        """Check if the connection is OK and able to communicate.
        
        Sometimes, the communication port of an instrument is open does not 
        mean the communication is OK. 

        For example, a raw serial com-port can be opened even if there is 
        nothing connected to it. So this method should be used to check if 
        the communication is working well. If the communication check failed, 
        an `InstrIOError` will be raised.

        This method should be performed at the end of the `__init__` method 
        of the specific Instrument Model classes.
        
        Raises:
            [InstrIOError][pyinst.errors.InstrIOError]
        """

    @classmethod
    def create(cls, *args: Any, **kwargs: Any) -> Optional[Self]:
        """Create an instance of the instrument model. If an exception is 
        raised during the instance creation, return None.
        
        Args:
            *args: Directly passed to the `__init__` method.
            **kwargs: Directly passed to the `__init__` method.

        Returns:
            The created instrument model instance, or None if the creation failed.
        """
        try:
            instance = cls(*args, **kwargs)
        except:
            instance = None
        return instance


class VisaInstrument(BaseInstrument):
    """Base class of VISA compatible instruments that use message based 
    communication.

    VisaInstrument creates a proxy object with `pyvisa` to communicate with 
    VISA compatible instruments.

    Refer to [PyVISA Documents](https://pyvisa.readthedocs.io/en/latest/index.html) 
    for more information.
    """

    def __init__(
            self, 
            resource_name: str, 
            read_termination: str = VI_READ_TERMINATION, 
            write_termination: str = VI_WRITE_TERMINATION, 
            timeout: int = VI_TIMEOUT, 
            open_timeout: int = VI_OPEN_TIMEOUT, 
            query_delay: float = VI_QUERY_DELAY, 
            encoding: str = "ascii",
            **kwargs: Any
        ):
        """
        Args:
            resource_name: Resource name or alias of the VISA resource to open.
            read_termination: Read termination character.
            write_termination: Write termination character.
            timeout: Timeout in milliseconds for all resource I/O operations.
            open_timeout: If the access_mode parameter requests a lock, then this 
                parameter specifies the absolute time period (in milliseconds) 
                that the resource waits to get unlocked before this operation 
                returns an error.
            query_delay: Delay in seconds between write and read operations.
            encoding: Encoding used for read and write operations.
            **kwargs: Directly passed to `rm.open_resource`.
        """
        super().__init__(resource_name=resource_name)
        rm = pyvisa.ResourceManager()
        self._inst: pyvisa.resources.MessageBasedResource = rm.open_resource(
            resource_name, read_termination=read_termination, 
            write_termination=write_termination, open_timeout=open_timeout, 
            timeout=timeout, query_delay=query_delay, encoding=encoding, **kwargs)
        self._check_communication()

    @property
    def resource_info(self) -> pyvisa.highlevel.ResourceInfo:
        """Get the (extended) information of the VISA resource."""
        return self._inst.resource_info

    @property
    def idn(self) -> str:
        """Returns a string that uniquely identifies the instrument."""
        return self.query('*IDN?')

    @property
    def opc(self) -> str:
        """Operation complete query."""
        return self.query('*OPC?')

    @property
    def stb(self) -> int:
        """Read status byte."""
        return int(self.query('*STB?'))

    def cls(self) -> None:
        """Clear instrument status"""
        self.command("*CLS")

    def close(self) -> None:
        """
        Closes the VISA session and marks the handle as invalid.
        """
        self._inst.close()

    def _check_communication(self) -> None:
        """Check if the connection is OK and able to communicate.

        Raises:
            [InstrIOError][pyinst.errors.InstrIOError]
        """
        try:
            idn = self.idn
            if not idn:
                raise ValueError("Empty IDN.")
        except pyvisa.VisaIOError as e:
            raise InstrIOError("Check communication failed.")

    def command(self, message: str) -> int:
        """
        Write a VISA command without read back.

        Alias of write(message).

        Args:
            message: The message to be sent.
        
        Returns:
            Number of bytes written.
        """
        return self.write(message)

    def write(
        self,
        message: str,
        termination: Optional[str] = None,
        encoding: Optional[str] = None,
    ) -> int:
        """Write a string message to the device.

        The write_termination is always appended to it.

        Args:
            message: The message to be sent.
            termination: Alternative character termination to use. If None, 
                the value of write_termination passed to `__init__` method is 
                used. Defaults to None.
            encoding: Alternative encoding to use to turn str into bytes. If 
                None, the value of encoding passed to `__init__` method is 
                used. Defaults to None.

        Returns:
            Number of bytes written.
        """
        return self._inst.write(message, termination, encoding)

    def read(
        self, termination: Optional[str] = None, encoding: Optional[str] = None
    ) -> str:
        """Read a string from the device.

        Reading stops when the device stops sending (e.g. by setting
        appropriate bus lines), or the termination characters sequence was
        detected.  Attention: Only the last character of the termination
        characters is really used to stop reading, however, the whole sequence
        is compared to the ending of the read string message.  If they don't
        match, a warning is issued.

        Args:
            termination: Alternative character termination to use. If None, 
                the value of write_termination passed to `__init__` method is 
                used. Defaults to None.
            encoding: Alternative encoding to use to turn bytes into str. If 
                None, the value of encoding passed to `__init__` method is 
                used. Defaults to None.

        Returns:
            Message read from the instrument and decoded.
        """
        return self._inst.read(termination, encoding)

    def query(self, message: str, delay: Optional[float] = None) -> str:
        """A combination of write(message) and read()

        Args:
            message: The message to send.
            delay: Delay in seconds between write and read operations. If 
                None, defaults to query_delay passed to `__init__` method.

        Returns:
            Answer from the device.

        """
        return self._inst.query(message, delay)

    def read_binary_values(
        self,
        datatype: pyvisa.util.BINARY_DATATYPES = "f",
        is_big_endian: bool = False,
        container: Type | Callable[[Iterable], Sequence] = list,
        header_fmt: pyvisa.util.BINARY_HEADERS = "ieee",
        expect_termination: bool = True,
        data_points: int = 0,
        chunk_size: Optional[int] = None,
    ) -> Sequence[int | float]:
        """Read values from the device in binary format returning an iterable
        of values.

        Args:
            datatype: Format string for a single element. See struct module. 
                'f' by default.
            is_big_endian: Are the data in big or little endian order. 
                Defaults to False.
            container: Container type to use for the output data. Possible 
                values are: list, tuple, np.ndarray, etc, Default to list.
            header_fmt: Format of the header prefixing the data. Defaults to 
                'ieee'.
            expect_termination: When set to False, the expected length of the 
                binary values block does not account for the final termination 
                character (the read termination). Defaults to True.
            data_points: Number of points expected in the block. This is used 
                only if the instrument does not report it itself. This will be 
                converted in a number of bytes based on the datatype. Defaults 
                to 0.
            chunk_size: Size of the chunks to read from the device. Using 
                larger chunks may be faster for large amount of data.

        Returns:
            Data read from the device.
        """
        return self._inst.read_binary_values(
            datatype, is_big_endian, container, header_fmt, 
            expect_termination, data_points, chunk_size)

    def query_binary_values(
        self,
        message: str,
        datatype: pyvisa.util.BINARY_DATATYPES = "f",
        is_big_endian: bool = False,
        container: Type | Callable[[Iterable], Sequence] = list,
        delay: Optional[float] = None,
        header_fmt: pyvisa.util.BINARY_HEADERS = "ieee",
        expect_termination: bool = True,
        data_points: int = 0,
        chunk_size: Optional[int] = None,
    ) -> Sequence[int | float]:
        """Query the device for values in binary format returning an iterable
        of values.

        Args:
            message: The message to send.
            datatype: Format string for a single element. See struct module. 
                'f' by default.
            is_big_endian: Are the data in big or little endian order. 
                Defaults to False.
            container: Container type to use for the output data. Possible 
                values are: list, tuple, np.ndarray, etc, Default to list.
            delay: Delay in seconds between write and read operations. If 
                None, defaults to query_delay passed to `__init__` method.
            header_fmt: Format of the header prefixing the data. Defaults to 
                'ieee'.
            expect_termination: When set to False, the expected length of the 
                binary values block does not account for the final termination 
                character (the read termination). Defaults to True.
            data_points: Number of points expected in the block. This is used 
                only if the instrument does not report it itself. This will be 
                converted in a number of bytes based on the datatype. Defaults 
                to 0.
            chunk_size: Size of the chunks to read from the device. Using 
                larger chunks may be faster for large amount of data.

        Returns:
            Data read from the device.

        """
        return self._inst.query_binary_values(
            message, datatype, is_big_endian, container, delay, 
            header_fmt, expect_termination, data_points, chunk_size)

    def set_visa_attribute(
        self, name: pyvisa.constants.ResourceAttribute, state: Any
    ) -> pyvisa.constants.StatusCode:
        """Set the state of an attribute in this resource.

        One should prefer the dedicated descriptor for often used attributes
        since those perform checks and automatic conversion on the value.

        Args:
            name: Attribute for which the state is to be modified.
            state: The state of the attribute to be set for the specified object.

        Returns:
            Return value of the library call.
        """
        return self._inst.set_visa_attribute(name, state)

    def get_visa_attribute(self, name: pyvisa.constants.ResourceAttribute) -> Any:
        """Retrieves the state of an attribute in this resource.

        One should prefer the dedicated descriptor for often used attributes
        since those perform checks and automatic conversion on the value.

        Args:
            name: Resource attribute for which the state query is made.

        Returns:
            The state of the queried attribute for a specified resource.
        """
        return self._inst.get_visa_attribute(name)


class ModelMDO34(VisaInstrument):

    brand = 'Tektronix'

    model = "MDO34"

    CH_NUMS = (1, 2, 3, 4)

    def __init__(self, resource_name: str, **kwargs: Any):
        super().__init__(resource_name, **kwargs)

    def _check_ch_num(self, ch_num) -> None:
        """
        Check if the channel number is valid. If not valid, an ValueError 
        will be raised.

        Args:
            ch_num: The channel number to check.

        Raises:
            ValueError
        """
        if ch_num not in self.CH_NUMS:
            raise ValueError(f"Invalid ch_num: {ch_num!r}")

    def _disable_response_header(self) -> None:
        """Disable the header in the responsed message of a query operation."""
        cmd = ":HDR OFF"
        self.command(cmd)

    def set_channel_label(self, ch_num: int, label: str) -> None:
        """
        Specifies the waveform label for a channel.

        Args:
            ch_num: The number of the channel. Valid values are: `1` | `2` | `3` | `4`
            label: The label of the channel. Limited to 30 characters
        """
        self._check_ch_num(ch_num)
        if not isinstance(label, str) or len(label) > 30:
            raise ValueError(f'Parameter label must be a str limited to 30 characters, but got {label!r}')
        cmd = f'CH{ch_num:d}:LABel "{label}"'
        self.command(cmd)
    
    def get_channel_label(self, ch_num: int) -> str:
        """Get the waveform label for a channel.
        
        Args:
            ch_num: The number of the channel. Valid values are: `1` | `2` | `3` | `4`

        Returns:
            The label of the channel. Limited to 30 characters.
        """
        self._check_ch_num(ch_num)
        cmd = f'CH{ch_num:d}:LABel?'
        return self.query(cmd).strip().strip('"')

    def set_channel_coupling(self, ch_num: int, coupling: str):
        """Specifies the input attenuator coupling setting for a channel.
        
        Args:
            ch_num: The number of the channel. Valid values are: `1` | `2` | `3` | `4`
            coupling: The attenuator coupling setting. Options are: `AC`, `DC`, `DCREJect`
        """
        self._check_ch_num(ch_num)
        if not coupling in {'AC', 'DC', 'DCREJect'}:
            raise ValueError(f'Invalid coupling: {coupling!r}')
        cmd = f'CH{ch_num:d}:COUPling {coupling}'
        self.command(cmd)

    def get_channel_coupling(self, ch_num: int) -> str:
        """Queries the specified input attenuator coupling setting for a channel.
        
        Args:
            ch_num: The number of the channel. Valid values are: `1` | `2` | `3` | `4`

        Returns:
            The attenuator coupling setting.
        """
        self._check_ch_num(ch_num)
        cmd = f'CH{ch_num:d}:COUPling?'
        return self.query(cmd).strip()

    def set_channel_bandwidth(self, ch_num: int, bandwidth: int | float) -> None:
        """"""
        self._check_ch_num(ch_num)
        if bandwidth <= 0:
            raise ValueError(f'Parameter bandwidth must be a positive float, but got {bandwidth!r}')
        cmd = f'CH{ch_num:d}:BANdwidth {bandwidth:.4E}'
        self.command(cmd)

    def get_channel_bandwidth(self, ch_num: int) -> float:
        self._check_ch_num(ch_num)
        cmd = f'CH{ch_num:d}:BANdwidth?'
        bw = float(self.query(cmd))
        return bw

    def set_channel_scale(self, ch_num: int, scale: int | float) -> None:
        """Specifies the vertical scale for the specified channel. 
        
        Args:
            ch_num: The number of the channel. Valid values are: `1` | `2` | `3` | `4`
            scale: The vertical channel scale in units-per-division. The unit is V. 
                The value entered here is truncated to three significant digits.
        """
        self._check_ch_num(ch_num)
        if scale <= 0:
            raise ValueError(f'Parameter scale must be a positive float, but got {scale!r}')
        cmd = f'CH{ch_num:d}:SCAle {scale:.3E}'
        self.command(cmd)

    def get_channel_scale(self, ch_num: int) -> float:
        """Queries the vertical scale for the specified channel. 
        
        Args:
            ch_num: The number of the channel. Valid values are: `1` | `2` | `3` | `4`
        
        Returns:
            The vertical channel scale in units-per-division. The unit is V.
        """
        self._check_ch_num(ch_num)
        cmd = f'CH{ch_num:d}:SCAle?'
        scale = float(self.query(cmd))
        return scale

    def set_channel_position(self, ch_num: int, position: int | float) -> None:
        """Specifies the vertical position of the channel.

        Args:
            ch_num: The number of the channel. Valid values are: `1` | `2` | `3` | `4`
            position: The position value in divisions, from the center graticule. The range is 8 to -8 divisions.
        """
        self._check_ch_num(ch_num)
        if not -8 <= position <= 8:
            raise ValueError(f'Parameter position must be between -8 and 8, but got {position!r}')
        cmd = f'CH{ch_num:d}:POSition {position:.3f}'
        self.command(cmd)

    def get_channel_position(self, ch_num: int) -> float:
        """Queries the vertical positon of the channel.
        
        Args:
            ch_num: The number of the channel. Valid values are: `1` | `2` | `3` | `4`

        Returns:
            The position value in divisions, from the center graticule. The range is 8 to -8 divisions.
        """
        self._check_ch_num(ch_num)
        cmd = f'CH{ch_num:d}:POSition?'
        position = float(self.query(cmd))
        return position

    def set_math_channel_type(self, num: int, math_type: str) -> None:
        """Specifies the math type.
        
        Args:
            num: The number of the math channel.
            math_type: The math type. Valid values are: `DUAL` | `FFT` | `ADVanced` | `SPECTRUM`
        """
        if math_type not in {'DUAL', 'FFT', 'ADVanced', 'SPECTRUM'}:
            raise ValueError(f'Invalid value for math_type: {math_type}')
        cmd = f'MATH{num:d}:TYPe {math_type}'
        self.command(cmd)

    def get_math_channel_type(self, num: int) -> str:
        """Gets the specified math type.
        
        Args:
            num: The number of the math channel.

        Returns:
            The math type.
        """
        cmd = f'MATH{num:d}:TYPe?'
        return self.query(cmd)

    def set_math_channel_function(self, num: int, function: str) -> None:
        """Define the math function with a text string.
        
        Args:
            num: The number of the math channel.
            function: The function definition.
        """
        cmd = f'MATH{num}:DEFine "{function}"'
        self.command(cmd)

    def get_math_channel_function(self, num: int) -> str:
        """Queries the math function defined.
        
        Args:
            num: The number of the math channel.
        
        Returns:
            The function definition.
        """
        cmd = f'MATH{num:d}:DEFine?'
        return self.query(cmd).strip().strip('"')
    
    def set_x_scale(self, scale: int | float) -> None:
        """Specifies the time base horizontal scale.
        
        Args:
            scale: The horizontal scale in seconds.
        """
        if not 400 * 10E-12 <= scale <= 1000:
            raise ValueError(f'Parameter scale must be between 400 * 10E-12 (400 ps) and 1000, but got {scale!r}')
        cmd = f'HORizontal:SCAle {scale:.4E}'

    def get_x_scale(self) -> float:
        """Queries the time base horizontal scale.
        
        Returns:
            The horizontal scale in seconds.
        """
        cmd = f'HORizontal:SCAle?'
        scale = float(self.query(cmd))
        return scale

    def set_x_position(self, position: int | float) -> None:
        """Specifies the horizontal position, in percent, that is used when delay is off.
        
        Args:
            position: The horisontal position in percent.
        """
        if not 0 <= position <= 100:
            raise ValueError(f'Parameter position must be between 0 and 100, but got {position!r}.')
        cmd = f'HORizontal:POSition {position!r}'
        self.command(cmd)

    def get_x_position(self) -> float:
        """Queries the horizontal position, in percent, that is used when delay is off.
        
        Returns:
            The horisontal position in percent.
        """
        cmd = f'HORizontal:POSition?'
        position = float(self.query(cmd))
        return position