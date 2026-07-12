from typing import Any, Dict
from pydantic import BaseModel
from pydantic import model_validator

from autogen_agentchat.base import Handoff
from drsai import (
    BaseTool,
    FunctionTool,
)

class DataAgentHandoff(Handoff):
    
    @model_validator(mode="before")
    @classmethod
    def set_defaults(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not values.get("description"):
            values["description"] = f"Handoff to {values['target']}."
        if not values.get("name"):
            values["name"] = f"transfer_to_{values['target']}".lower()
        else:
            name = values["name"]
            if not isinstance(name, str):
                raise ValueError(f"Handoff name must be a string: {values['name']}")
            # Check if name is a valid identifier.
            if not name.isidentifier():
                raise ValueError(f"Handoff name must be a valid identifier: {values['name']}")
        if not values.get("message"):
            values["message"] = (
                f"由```{values['target']}```进行接下来的操作, 现在由```{values['target']}```接手."
            )
        return values

    @property
    def handoff_tool(self) -> BaseTool[BaseModel, BaseModel]:
        """Create a handoff tool from this handoff configuration."""

        def _handoff_tool(reason: str) -> str:
            """
            args: 
                reason: str, the reason for the handoff
            """
            return f"{reason}\n\n{self.message}\n"

        return FunctionTool(_handoff_tool, name=self.name, description=self.description, strict=True)
    