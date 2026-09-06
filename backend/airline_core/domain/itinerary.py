from dataclasses import dataclass
from datetime import datetime, timedelta

from .errors import ValidationError


@dataclass(frozen=True, slots=True)
class SegmentTime:
    origin: str
    destination: str
    departure: datetime
    arrival: datetime


def validate_itinerary(segments: list[SegmentTime]) -> None:
    if not 1 <= len(segments) <= 2:
        raise ValidationError("Itinerary must contain one or two segments")
    if any(s.arrival <= s.departure for s in segments):
        raise ValidationError("Invalid segment chronology")
    if len(segments) == 2:
        first, second = segments
        layover = second.departure - first.arrival
        if first.destination != second.origin:
            raise ValidationError("Connection airport is not continuous")
        if not timedelta(minutes=45) <= layover <= timedelta(hours=6):
            raise ValidationError("Connection must be 45m to 6h")
