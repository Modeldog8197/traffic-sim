"""Versioned input contracts. Schema 1 remains readable; writes use schema 2."""
from typing import Annotated, Literal
from pydantic import BaseModel, Field, model_validator

Green = Annotated[int, Field(ge=10, le=90)]

class RoadEdit(BaseModel):
    closed: bool = False
    speed: float = Field(11.11, ge=2, le=30)
    allowed: list[Literal['passenger', 'bus']] = ['passenger', 'bus']

class ODPair(BaseModel):
    origin: str
    destination: str
    weight: float = Field(1, gt=0, le=1000)

class BusStop(BaseModel):
    edge: str
    lane: int = Field(0, ge=0)
    position: float = Field(100, ge=5)
    dwell: float = Field(20, ge=0, le=300)

class TransitLine(BaseModel):
    id: str = Field('B1', pattern=r'^[A-Za-z0-9_-]{1,30}$')
    route: list[str] = Field(min_length=2, max_length=100)
    stops: list[BusStop] = []
    headway: int = Field(120, ge=15, le=3600)
    first_departure: int = Field(0, ge=0)
    departures: list[Annotated[float, Field(ge=0)]] = Field(default_factory=list, max_length=200)

class Scenario(BaseModel):
    schema_version: Literal[2] = 2
    name: str = Field('Baseline', min_length=1, max_length=80)
    network: str = 'synthetic'
    network_version: str | None = None
    duration: int = Field(600, ge=60, le=3600)
    clearance: int = Field(180, ge=0, le=1800)
    warmup: int = Field(0, ge=0)
    seed: int = Field(42, ge=0, le=2147483647)
    demand: int = Field(240, ge=1, le=2000)
    pattern: Literal['uniform', 'peak'] = 'uniform'
    bus_fraction: float = Field(.08, ge=0, le=.5)
    controller: Literal['fixed', 'responsive', 'pressure'] = 'fixed'
    green: Green = 30
    min_green: int = Field(10, ge=10, le=30)
    max_green: int = Field(60, ge=30, le=90)
    transit_extension: int = Field(0, ge=0, le=10)
    pressure_downstream: bool = True
    car_occupancy: float = Field(1.5, ge=1, le=8)
    bus_occupancy: float = Field(30, ge=1, le=60)
    transit: list[TransitLine] = Field(default_factory=list, max_length=10)
    corridors: dict[str, list[str]] = {}
    routing: Literal['departure_fastest'] = 'departure_fastest'
    roads: dict[str, RoadEdit] = {}
    od: list[ODPair] = Field(default_factory=list, max_length=100)
    signals: dict[str, dict[int, Green]] = {}

    @model_validator(mode='before')
    @classmethod
    def migrate(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            version = value.get('schema_version', 1)
            if version not in (1, 2):
                raise ValueError('Unsupported scenario schema; upgrade CityLab before importing.')
            value['schema_version'] = 2
        return value

    @model_validator(mode='after')
    def coherent(self):
        if self.warmup >= self.duration:
            raise ValueError('Warm-up must be shorter than demand duration.')
        if self.min_green > self.max_green:
            raise ValueError('Minimum green exceeds maximum green.')
        if len({line.id for line in self.transit}) != len(self.transit):
            raise ValueError('Bus line IDs must be unique.')
        if '/' in self.network or '..' in self.network:
            raise ValueError('Invalid network identifier')
        return self

class SearchSpace(BaseModel):
    greens: list[Green] = Field(default_factory=lambda: [15, 30, 45], max_length=8)
    controllers: list[Literal['fixed', 'responsive', 'pressure']] = ['fixed', 'responsive', 'pressure']
    transit_extensions: list[Annotated[int, Field(ge=0, le=10)]] = [0]
    junction_greens: dict[str, list[Green]] = {}
    road_speeds: dict[str, list[Annotated[float, Field(ge=2, le=30)]]] = {}
    road_access: dict[str, list[Literal['all', 'bus_only', 'closed']]] = {}

class ExperimentSpec(BaseModel):
    schema_version: Literal[2] = 2
    name: str = Field('Neighbourhood intervention study', min_length=1, max_length=100)
    scenario: Scenario
    mode: Literal['quick', 'research'] = 'quick'
    space: SearchSpace = Field(default_factory=SearchSpace)
    search_seed: int = Field(2026, ge=0, le=2147483647)
    max_candidates: int = Field(4, ge=1, le=48)
    finalists: int = Field(1, ge=1, le=3)
    budget: int = Field(60, ge=4, le=1200)
    search_seeds: list[int] = [11, 12]
    tuning_seeds: list[int] = [31]
    evaluation_seeds: list[int] = [101, 102]
    conditions: list[Literal['uniform', 'peak', 'high_demand', 'bus_mix', 'disruption']] = ['uniform', 'peak']
    disruption_road: str | None = None
    objectives: list[Literal['full_demand_loss', 'person_loss', 'mean', 'delay', 'bus_mean', 'queue_seconds', 'od_inequality', 'co2_kg']] = ['full_demand_loss', 'person_loss']
    min_completion: float = Field(.75, ge=0, le=1)
    max_completion_drop: float = Field(0, ge=0, le=.2)
    max_invalid_fraction: float = Field(.1, ge=0, le=1)
    ablations: bool = True

    @model_validator(mode='after')
    def protocol(self):
        groups = [self.search_seeds, self.tuning_seeds, self.evaluation_seeds]
        if any(not g or len(g) != len(set(g)) or len(g) > 30 for g in groups):
            raise ValueError('Each stage needs 1–30 unique seeds.')
        if any(not 0 <= seed <= 2147483647 for g in groups for seed in g):
            raise ValueError('Seeds must be between 0 and 2147483647.')
        if len(set(sum(groups, []))) != sum(map(len, groups)):
            raise ValueError('Search, tuning and held-out seeds must be disjoint.')
        if self.mode == 'research' and len(self.evaluation_seeds) < 10:
            raise ValueError('Research mode requires at least ten held-out seeds per condition.')
        if not self.conditions or not self.objectives:
            raise ValueError('Select at least one condition and objective.')
        if 'disruption' in self.conditions and not self.disruption_road:
            raise ValueError('Choose a road for the disruption condition.')
        if len(set(self.conditions)) != len(self.conditions):
            raise ValueError('Conditions must be unique.')
        return self
