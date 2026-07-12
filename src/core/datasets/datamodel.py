from datetime import datetime
from enum import Enum
from typing import Any, List, Optional, Union, Dict

from autogen_core import ComponentModel
from pydantic import field_serializer
from sqlalchemy import ForeignKey, Integer
from sqlmodel import JSON, Column, DateTime, Field, SQLModel, func

class ToolsRunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    STOPPED = "stopped"
    AWAITING_INPUT = "awaiting_input"
    PAUSED = "paused"

class ToolsStatus(SQLModel, table=True):
    __table_args__ = {"sqlite_autoincrement": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )  # pylint: disable=not-callable
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now()),
    )  # pylint: disable=not-callable
    version: Optional[str] = "0.0.1"
    # task info
    user_id: Optional[str] = None # email or other unique identifier
    thread_id: Optional[str] = None # unique identifier for the conversation thread

    first_user_handle_info: Optional[str] = None # json string of first user handle info
    verified_dict: Optional[str] = None # json string of verified dict for get the original cif file path
    rongzai_status: ToolsRunStatus = Field(default=ToolsRunStatus.COMPLETE) #蓉仔的状态，有COMPLETE、RUNNING、AWAITING_INPUT三种情况
    gsas_ii_status: ToolsRunStatus = Field(default=ToolsRunStatus.AWAITING_INPUT) #GSAS-II工具的状态，有RUNNING、AWAITING_INPUT两种情况
    gsas_ii_input: Optional[str] = None # GSAS-II工具的输入参数
    gsas_ii_output: Optional[str] = None # GSAS-II工具的输出结果
    report_content: Optional[str] = None #生成的报告内容

    #######下面的暂时不用########
    
    user_handle_info: Optional[str] = None # json string of user handle info
    agent_handle_info: Optional[str] = None # json string of agent handle info
    
    # pdf tool info
    pdf_status: ToolsRunStatus = Field(default=ToolsRunStatus.CREATED)
    pdf_params: Optional[str] = None # json string of output
    pdf_output: Optional[str] = None # json string of output

    # AIndex tool info
    AIndex_status: ToolsRunStatus = Field(default=ToolsRunStatus.CREATED)
    AIndex_params: Optional[str] = None # json string of output
    AIndex_output: Optional[str] = None # json string of output

    # NPD_Simulator tool info
    NPD_Simulator_status: ToolsRunStatus = Field(default=ToolsRunStatus.CREATED)
    NPD_Simulator_params: Optional[str] = None # json string of output
    NPD_Simulator_output: Optional[str] = None # json string of output

    


