from dataclasses import asdict
from collections import Counter
from typing import Dict, Any, ClassVar
from worlds.AutoWorld import World, WebWorld
from BaseClasses import ItemClassification, Region, Tutorial

from .Items import RustedMossItem, item_dict
from .Locations import RustedMossLocation, location_list
from .Options import RustedMossOptions, Ending
from .LogicExtractor import extract_logic
from ..generic.Rules import set_rule


class RMWeb(WebWorld):
    setup_en = Tutorial(
        "Setup Guide",
        "A guide to playing Rusted Moss with Archipelago.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Mr. L"]
    )

    tutorials = [setup_en]


class RustedMossWorld(World):
    """
    Rusted Moss is a metroidvania featuring an elastic physics-based grappling hook.
    """

    game = "Rusted Moss"
    web = RMWeb()
    options_dataclass = RustedMossOptions
    options: RustedMossOptions
    topology_present = True
    base_id = 144000000
    item_name_to_id = {item: id for id, item in enumerate(item_dict.keys(), base_id)}
    location_name_to_id = {location: id for id, location in enumerate(location_list, base_id)}
    # Location: Region for locations that only have one connection
    location_to_region: ClassVar[dict[str, str]] = {}
    # Event names
    events: ClassVar[set] = set()
    # Extracted rule definitions {(parent, spot), rule_string} where spot may be a Location, Region, or Event
    rules: ClassVar[dict[tuple[str, str], str]] = {}

    def create_item(self, item: str) -> RustedMossItem:
        return RustedMossItem(item, item_dict[item][0], self.item_name_to_id[item], self.player)

    def create_event(self, locationName, itemName, region) -> RustedMossLocation:
        event = RustedMossLocation(self.player, locationName, None, region)
        event.place_locked_item(RustedMossItem(itemName, ItemClassification.progression, None, self.player))
        return event

    @classmethod
    def stage_generate_early(cls, multiworld) -> None:
        (cls.events, cls.rules) = extract_logic()
        location_connections = Counter()
        cls.location_to_region = {}
        for parent, target in cls.rules.keys():  # intentionally keys()
            if target not in cls.location_name_to_id and target not in cls.events:
                continue
            location_connections[target] += 1
            if location_connections[target] == 1:
                cls.location_to_region[target] = parent
            elif location_connections[target] == 2:
                del cls.location_to_region[target]
                # remove any locations with more than one connection as they need a proxy region

    def create_regions(self) -> None:
        regions = {}
        location_rules = {}

        def get_parent(name: str) -> Region:
            """
            Grab region by name, creating it if missing,
            and grabbing a location's parent region if it doesn't need a proxy region
            """
            if name not in regions:
                if name in self.location_to_region:
                    # locations that have one parent region and don't need a proxy region
                    return get_parent(self.location_to_region[name])
                regions[name] = Region(name, self.player, self.multiworld)
            return regions[name]

        get_parent("Menu").connect(get_parent("rm_start_0[100390]"))  # this could be a different origin_region_name too
        for key, rule in self.rules.items():
            parent, target = key
            logic = None if rule == "" else self.convert_to_rule(rule)
            if target in self.location_to_region:
                # if a location is in this lookup it doesn't need a proxy region, save the logic for later and skip
                location_rules[target] = logic
                continue
            get_parent(parent).connect(get_parent(target), rule=logic)

        for event in self.events:
            eventLocation = self.create_event(event, event, get_parent(event))
            eventLocation.show_in_spoiler = False
            rule = location_rules.get(event)
            if rule:
                set_rule(eventLocation, rule)
            get_parent(event).locations.append(eventLocation)

        for location in self.location_name_to_id.keys():
            loc = RustedMossLocation(self.player, location, self.location_name_to_id[location], get_parent(location))
            rule = location_rules.get(location)
            if rule:
                set_rule(loc, rule)
            get_parent(location).locations.append(loc)

        self.multiworld.regions += list(regions.values())

    def create_items(self) -> None:
        for item_key, item_value in item_dict.items():
            for count in range(item_value[1]):
                self.multiworld.itempool.append(self.create_item(item_key))

    def set_rules(self) -> None:
        goal_event = "e_goal_e"
        if self.options.ending.value == Ending.option_ending_a:
            goal_event = "e_goal_a"
        elif self.options.ending.value == Ending.option_ending_b:
            goal_event = "e_goal_b"
        elif self.options.ending.value == Ending.option_ending_c:
            goal_event = "e_goal_c"
        elif self.options.ending.value == Ending.option_ending_d:
            goal_event = "e_goal_d"
        elif self.options.ending.value == Ending.option_ending_e:
            goal_event = "e_goal_e"
        self.multiworld.completion_condition[self.player] = lambda state: state.has(goal_event, self.player)

    def convert_to_rule(self, rule):
        def make_has(item: str, count: int) -> str:
            if count > 1:
                return f'state.has("{item}", {self.player}, {count})'
            else:
                return f'state.has("{item}", {self.player})'

        part_lookup = {
            **{c: c for c in "()"},
            "+": " and ",
            "|": " or ",
            **{i: make_has(i, 1) for i in item_dict.keys()},
            "Grappling_Hook_Upgrade": make_has("Grappling_Hook", 2),
            "Infinite_Grapple": make_has("Grappling_Hook", 3),
            **{name: str(bool(value)) for name, value in asdict(self.options).items()},
            **{i: make_has(i, 1) for i in self.events},
        }

        lambda_string = "lambda state: "
        parts = rule.replace("(", "( ").replace(")", " )").split()
        for part in parts:
            splitPart = part.split("{")

            if part in part_lookup:
                lambda_string += part_lookup[part]
            elif splitPart[0] in item_dict.keys():
                lambda_string += make_has(splitPart[0], int(splitPart[1].split("}")[0]))
            else:
                print("unexpected part of rule")
                print(part)

        # print("lambda_string: " + lambda_string)
        return eval(lambda_string)

    def fill_slot_data(self) -> Dict[str, Any]:
        return {
            "ending": self.options.ending.value,
            "hard_maya": self.options.hard_maya.value,
            "deathlink": self.options.deathlink.value,
            "damage_boost": self.options.damage_boost.value,
            "grenade_boost": self.options.grenade_boost.value,
            "precise_movement": self.options.precise_movement.value,
            "precise_grapple": self.options.precise_grapple.value,
            "bunny_hopping": self.options.bunny_hopping.value,
            "hard_combat": self.options.hard_combat.value,
            "shop_discount_percentage": self.options.shop_discount_percentage.value,
        }
