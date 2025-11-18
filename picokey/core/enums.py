import enum

class NamedIntEnum(enum.IntEnum):
    def __str__(self):
        return self.name
