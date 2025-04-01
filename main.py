from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, ResultContentType
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
import re
import xml.etree.ElementTree as ET
import traceback

@register("astrbot_plugin_Merge_WeMSG", "Jackson", "支持微信个人号(gewechat)的合并消息处理和转发", "1.0.0")
class MergeWeMSGPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 设置插件优先级为最高
        self._priority = -999999  # 使用更小的值确保最高优先级
        logger.info(f"合并消息处理插件已加载，优先级：{self._priority}")
    
    @property
    def priority(self) -> int:
        """插件优先级，数字越小优先级越高"""
        return self._priority

    @priority.setter
    def priority(self, value: int):
        self._priority = value
        logger.info(f"插件优先级已更新为：{value}")
    
    async def handle_event(self, event: AstrMessageEvent) -> bool:
        """处理事件的主要逻辑"""
        try:
            logger.info("开始处理消息事件...")
            
            # 检查是否为gewechat平台
            platform_name = event.get_platform_name()
            logger.info(f"当前消息平台：{platform_name}")
            if platform_name != 'gewechat':
                logger.debug(f"不是gewechat平台的消息，当前平台：{platform_name}")
                return False
            
            logger.info("检测到gewechat平台消息")
                
            # 检查是否为合并消息类型(MsgType=49)
            raw_message = event.message_obj.raw_message
            logger.debug(f"原始消息内容: {raw_message}")
            
            if not raw_message:
                logger.debug("没有原始消息内容")
                return False
                
            # 直接检查MsgType
            msg_type = raw_message.get('MsgType')
            if msg_type != 49:
                logger.debug(f"不是合并消息类型(MsgType=49), 当前类型: {msg_type}")
                return False
            
            logger.info("检测到合并消息类型")
                
            # 获取Content内容
            content = raw_message.get('Content', {})
            if isinstance(content, dict):
                content_str = content.get('string', '')
            else:
                content_str = str(content)
                
            if not content_str:
                logger.debug("Content中没有string字段")
                return False
                
            # 判断是否为合并消息
            if '<appmsg' not in content_str:
                logger.debug("不是合并消息格式")
                return False
            
            logger.info("开始解析XML内容...")
            
            # 解析XML内容
            root = ET.fromstring(content_str)
            appmsg = root.find('appmsg')
            if appmsg is None:
                logger.debug("找不到appmsg节点")
                return False
            
            # 检查是否为聊天记录类型
            appmsg_type = appmsg.find('type')
            if appmsg_type is None or appmsg_type.text != '19':
                logger.debug(f"不是聊天记录类型, type: {appmsg_type.text if appmsg_type else 'None'}")
                return False
                
            # 获取标题和记录内容
            title = appmsg.find('title')
            if title is None:
                logger.debug("找不到title节点")
                return False
                
            recorditem = appmsg.find('recorditem')
            if recorditem is None:
                logger.debug("找不到recorditem节点")
                return False
                
            # 解析recorditem内容
            recordinfo_text = recorditem.text
            if not recordinfo_text:
                logger.debug("recorditem内容为空")
                return False
                
            # 解析recordinfo
            recordinfo = ET.fromstring(recordinfo_text)
            
            # 获取聊天记录的标题
            chat_title = recordinfo.find('title')
            if chat_title is None:
                logger.debug("找不到聊天记录标题")
                return False
                
            # 获取所有聊天记录条目
            datalist = recordinfo.find('datalist')
            if datalist is None:
                logger.debug("找不到datalist节点")
                return False
                
            logger.info("开始解析聊天记录...")
            
            # 解析每条聊天记录
            messages = []
            for dataitem in datalist.findall('dataitem'):
                datatype = dataitem.get('datatype')
                
                # 获取发送者名称
                sourcename = dataitem.find('sourcename')
                if sourcename is None:
                    continue
                    
                # 获取发送时间
                sourcetime = dataitem.find('sourcetime')
                if sourcetime is None:
                    continue
                    
                time_parts = sourcetime.text.split()
                time_only = time_parts[1] if len(time_parts) > 1 else "未知时间"
                
                # 根据数据类型处理不同的消息内容
                if datatype == '1':  # 文本消息
                    datadesc = dataitem.find('datadesc')
                    if datadesc is not None and datadesc.text:
                        messages.append(f"{time_only} - {sourcename.text}：{datadesc.text}")
                elif datatype == '2':  # 图片消息
                    messages.append(f"{time_only} - {sourcename.text}：[图片]")
                elif datatype == '3':  # 语音消息
                    messages.append(f"{time_only} - {sourcename.text}：[语音]")
                elif datatype == '4':  # 视频消息
                    messages.append(f"{time_only} - {sourcename.text}：[视频]")
                elif datatype == '5':  # 文件消息
                    messages.append(f"{time_only} - {sourcename.text}：[文件]")
                else:
                    messages.append(f"{time_only} - {sourcename.text}：[未知类型消息]")
            
            # 如果没有解析到任何消息
            if not messages:
                logger.debug("没有解析到任何消息")
                return False
                
            # 获取聊天记录日期（从第一条消息的时间中提取）
            date_parts = sourcetime.text.split()
            chat_date = date_parts[0] if len(date_parts) > 0 else "未知日期"
            
            # 构建格式化的合并消息文本
            formatted_message = f"合并消息：{chat_title.text}\n消息日期：{chat_date}\n对话内容：\n" + "\n".join(messages)
            
            # 发送到LLM进行处理
            logger.info(f"已处理合并消息，准备发送给LLM：\n{formatted_message}")
            
            # 修改原始消息对象
            event.message_obj.message = [Comp.Plain(formatted_message)]
            event.message_str = formatted_message
            
            logger.info("消息处理完成，返回True")
            return True
            
        except Exception as e:
            logger.error(f"处理合并消息时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    @filter.platform_adapter_type(filter.PlatformAdapterType.GEWECHAT)
    async def on_message(self, event: AstrMessageEvent):
        '''处理微信合并消息'''
        logger.info("插件收到消息，开始处理...")
        # 如果成功处理了合并消息，就不需要继续处理
        if await self.handle_event(event):
            logger.info("合并消息处理成功，准备发送给LLM...")
            # 使用request_llm发送消息给LLM
            yield event.request_llm(
                prompt=event.message_str,  # 使用处理后的消息内容
                func_tool_manager=self.context.get_llm_tool_manager(),  # 获取函数调用管理器
                session_id=None,  # 不指定会话ID，让系统自动处理
                contexts=[],  # 不提供上下文
                system_prompt="",  # 不提供系统提示
                image_urls=[]  # 不提供图片
            )
            logger.info("消息已发送给LLM")
        logger.info("消息处理完成")

    async def terminate(self):
        '''插件终止时的清理工作'''
        logger.info("合并消息处理插件已卸载")
