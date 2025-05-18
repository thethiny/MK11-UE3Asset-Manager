from enum import Enum, IntEnum
from typing import Dict, Type


class CompressionType(IntEnum):
    NONE  = 0x0000
    ZLIB  = 0x0001
    LZO   = 0x0002
    LZX   = 0x0004
    PFS   = 0x0008
    PS4   = 0x0010
    XBX   = 0x0040
    OODLE = 0x0100

class MK11UnlockableType(IntEnum):
    kUnlockNone              = 0x0
    kUnlockGeneral           = 0x1
    kUnlockBackground        = 0x2
    kUnlockCharacter         = 0x3
    kUnlockPlayerBadgeIcon   = 0x4
    kUnlockPlayerBadgeBgnd   = 0x5
    kUnlockModifier          = 0x6
    kUnlockAOC               = 0x7
    kUnlockInventoryItem     = 0x8
    kUnlockLoadoutSlot       = 0x9
    kUnlockInventorySpace    = 0xA
    kUnlockLootChest         = 0xB
    kUnlockEmoji             = 0xC
    kUnlockKollection        = 0xD
    kUnlockKrypt             = 0xE
    kUnlockAnnouncer         = 0xF

class EItemRarityType(IntEnum):
    NONE    = 0x00
    Rarity1 = 0x01
    Rarity2 = 0x02
    Rarity3 = 0x03
    Rarity4 = 0x04
    Max     = 0x05
    Normal  = 0x06
    Mortal  = 0x07
    Mythic  = 0x08
    Elder   = 0x09

class EInventoryItemType(IntEnum):
    Instanced  = 0x00
    Stackable  = 0x01
    Unlockable = 0x02

class EItemUnlockableType(IntEnum):
    NONE                           = 0x00
    AIBattlesLootPool              = 0x01
    CharacterPortals               = 0x02
    CharacterTraining              = 0x03
    ErmacBodyLootTable             = 0x04
    Forge                          = 0x05
    KenshiChestLootTable           = 0x06
    KollectorStore                 = 0x07
    KombatLeague                   = 0x08
    KronikaChestLootTable          = 0x09
    Krypt                          = 0x0A
    KryptNormalChests              = 0x0B
    NormalChestLootTable           = 0x0C
    PremierAndBossPortals          = 0x0D
    RAT                            = 0x0E
    Story                          = 0x0F
    SandsOfTime                    = 0x10
    TOTTutorial                    = 0x11
    TowersRewards                  = 0x12
    KryptLootTables_ErmacChests    = 0x13
    KryptLootTables_HeadSpikes     = 0x14
    KryptLootTables_KenshiChests   = 0x15
    KryptLootTables_KollectorStore = 0x16
    KryptLootTables_KronikaChests  = 0x17
    KryptLootTables_NetherForge    = 0x18
    KryptLootTables_NormalChests   = 0x19
    KryptLootTables_Restock1       = 0x1A
    KryptLootTables_Restock2       = 0x1B
    KryptLootTables_Restock3       = 0x1C
    KryptLootTables_ScorpionChests = 0x1D
    KryptLootTables_ShaoKahnChests = 0x1E
    KryptLootTables_Shrine         = 0x1F
    KryptLootTables_ThroneRoom     = 0x20
    PortalHourly                   = 0x21
    PortalAssist                   = 0x22
    PortalDaily                    = 0x23
    PortalKey                      = 0x24
    PortalTeam                     = 0x25

class EAttributeParameterType(IntEnum):
    String             = 0x00
    Int                = 0x01
    Float              = 0x02
    Percent            = 0x03
    Context_Character  = 0x04
    CharacterAttribute = 0x05

class EAttributeModeRestrictionType(IntEnum):
    Any        = 0x00
    Multiverse = 0x01
    AI         = 0x02
    Online     = 0x03

class EKollectionCategoryType(IntEnum):
    NONE         = 0x00
    Characters   = 0x01
    Environments = 0x02
    Story        = 0x03
    Endings      = 0x04
    Music        = 0x05
    FanArt       = 0x06
    Recipes      = 0x07
    Max          = 0x08

class EInventoryHideGroupType(IntEnum):
    NONE            = 0x00
    Hidden          = 0x01
    HiddenGroup1    = 0x02
    HiddenGroup2    = 0x03
    HiddenGroup3    = 0x04
    HiddenGroup4    = 0x05
    HiddenGroup5    = 0x06
    HiddenGroup6    = 0x07
    HiddenGroup7    = 0x08
    HiddenGroup8    = 0x09
    HiddenGroup9    = 0x0A
    HiddenGroup10   = 0x0B
    HiddenGroup11   = 0x0C
    HiddenGroup12   = 0x0D
    HiddenGroup13   = 0x0E
    HiddenGroup14   = 0x0F
    HiddenGroup15   = 0x10
    HiddenGroup16   = 0x11

class EItemMoveInfoBlockType(IntEnum):
    NONE            = 0x00
    Low             = 0x01
    Med             = 0x02
    High            = 0x03
    Overhead        = 0x04

class EInventoryGenerationType(IntEnum):
    Release         = 0x00
    Full            = 0x01
    Generated       = 0x02
    Linked          = 0x03
    QA_Linked       = 0x04
    QA_Attributes   = 0x05

enumMaps: Dict[str, Type[Enum]] = {
    "mUnlockType": MK11UnlockableType,
    "mRarity": EItemRarityType,
    "Rarity": EItemRarityType,
    "mType": MK11UnlockableType,
    "mCategory": EKollectionCategoryType,  # Can be multiple, depends on file type and such
    "InventoryItemType": EInventoryItemType,
    "UnlockableType": EItemUnlockableType,
    "Mode": EAttributeModeRestrictionType,  # Can be multiple, depends on file type and such
    "Type": EAttributeParameterType,  # Can be multiple, depends on file type and such
    "MoveInfoBlockType": EItemMoveInfoBlockType,
    "HideGroup": EInventoryHideGroupType,
}
