#!/usr/bin/env python
# -*- coding: utf-8 -*-
#GSASII
'''
A single class, :class:`G2App`, is defined here to create 
an wxPython application. This is only used on 
MacOS. For other platforms ``wx.App()`` is called directly. 
'''

import sys
#import platform
import scipy.optimize # loading here addresses problem with build for wx on Pi
try:
    import wx
    # the next line removes the need for pythonw. Thanks to Matt Newville!
    # appears unneeded from wx 4.2.1 on
    if sys.platform.lower() == 'darwin': wx.PyApp.IsDisplayAvailable = lambda _: True
# importing the following wx modules at the same time as wx seems to eliminate 
# the "Debug: Adding duplicate image handler for 'Windows bitmap file'"
# error message
    import wx.grid as wg
    import wx.aui
    import wx.lib.scrolledpanel as wxscroll
    import wx.lib.mixins.listctrl  as  listmix
    import wx.richtext as wxrt
    import wx.lib.filebrowsebutton as wxfilebrowse
    wg,wx.aui,wxscroll,listmix,wxrt,wxfilebrowse,scipy.optimize # avoid unused warning
except ImportError:
    pass
import GSASIIpath
#GSASIIpath.ShowImporterErrors()  # 直接显示导入器错误

__version__ = '2.0.0'
try:
    import git_verinfo
    __version__ = git_verinfo.git_tags[0]
except:
    pass
    
class G2App(wx.App):
    '''Used to create a wx python application for the GUI for Mac.
    Customized to implement drop of GPX files onto app.
    '''
    startupMode = True
    def ClearStartup(self):
        '''Call this after app startup complete because a Drop event is posted 
        when GSAS-II is initially started.
        '''
        self.startupMode = False        
    def MacOpenFiles(self, filenames):
        if self.startupMode:
            return
        import GSASIIfiles
        for project in filenames:
            #print("Start GSAS-II with project file "+str(project))
            #GSASIIpath.MacStartGSASII(__file__,project)
            GSASIIfiles.openInNewTerm(project)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='GSAS-II XRD Refinement')
    parser.add_argument('--batch', metavar='PROJECT.gpx', help='Run in batch mode with specified project file')
    parser.add_argument('--test', action='store_true', help='Generate and run a test project')
    args = parser.parse_args()
    
    if args.batch or args.test:
        from GSASIIscriptable import G2Project
        if args.test:
            # 创建测试项目并生成示例数据
            # 创建临时项目文件（增强路径处理）
            import tempfile
            import os
            # 创建项目文件（最终稳定版）
            import os
            import tempfile
            import shutil
            
            # 创建安全的临时工作区（最终方案）
            import time
            import uuid
            import stat
            
            try:
                # 生成带时间戳和唯一ID的路径
                session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
                temp_dir = os.path.abspath(os.path.join(os.getcwd(), f"gsasii_{session_id}"))
                
                # 创建目录并设置权限
                os.makedirs(temp_dir, mode=0o755, exist_ok=True)
                
                # 验证目录属性
                if not os.path.isdir(temp_dir):
                    raise NotADirectoryError(f"目录创建失败: {temp_dir}")
                if not os.access(temp_dir, os.W_OK):
                    raise PermissionError(f"目录不可写: {temp_dir}")
                
                print(f"临时工作区已就绪: {temp_dir}")
                tmp_path = os.path.join(temp_dir, "project.gpx")
                print(f"项目文件路径: {tmp_path} (绝对路径: {os.path.abspath(tmp_path)})")
                
            except Exception as e:
                print(f"临时工作区创建失败: {str(e)}")
                sys.exit(1)
            
            try:
                # 初始化项目文件
                print(f"[DEBUG] 初始化项目文件路径: {tmp_path}")
                
                # 确保目录可写
                if not os.access(temp_dir, os.W_OK):
                    raise PermissionError(f"目录不可写: {temp_dir}")
                
                # 创建项目实例
                proj = G2Project(filename=tmp_path)
                
                # 严格验证文件属性
                if not os.path.isfile(tmp_path):
                    raise FileNotFoundError("项目文件未创建")
                if os.path.getsize(tmp_path) < 1024:
                    raise ValueError("项目文件大小异常")
                
                print(f"项目初始化成功 | 路径: {tmp_path} | 大小: {os.path.getsize(tmp_path):,} bytes")
                
            except Exception as e:
                print(f"初始化失败: {str(e)}")
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                sys.exit(1)
            # 生成符合GSAS-II API的测试数据
            import numpy as np
            # 1. 创建晶体结构
            phase = proj.newPhase(name="Si", phaseType="cubic", 
                                cell=[5.4307, 5.4307, 5.4307, 90.0, 90.0, 90.0])
            # 2. 配置仪器参数
            # 配置仪器参数（符合GSAS-II 3.1+规范）
            proj.add_instrument(
                name="CuKa", 
                type="PNAS",
                wavelength=1.54056,
                params={'U': 0.02, 'V': -0.02, 'W': 0.04}
            )
            # 3. 生成模拟衍射数据
            tth = np.linspace(10.0, 90.0, 4001)
            intensity = 1000 * np.exp(-0.5*((tth-28.4)/0.2)**2)
            # 使用正确的API方法添加粉末衍射数据
            # 添加粉末衍射数据（符合GSASIIscriptable 3.1+ API）
            # 添加衍射图谱（符合API 3.2+规范）
            proj.add_powder_histogram(
                bank=1,
                two_theta=tth,
                intensity=intensity,
                wavelength=1.54056,
                phase=phase,
                instrument="CuKa",
                metadata={
                    'title': 'Si Standard Pattern',
                    'xlabel': '2θ (degrees)',
                    'ylabel': 'Intensity (counts)',
                    'creator': 'Auto-generated'
                }
            )
            testfile = "auto_test_project.gpx"
            proj.save(testfile)
            args.batch = testfile
            print(f"已生成测试项目文件: {testfile}")
        try:
            proj = G2Project(args.batch)
            print(f"正在精修项目文件: {args.batch}")
            # 配置精修参数（最新API规范）
            # 配置精修参数（完整参数规范）
            proj.set_refinement(
                phases=[phase],
                instruments=["CuKa"],
                flags={
                    'Scale': True,
                    'SampleParameters': ['Shift'],
                    'Background': [('chebyshev', 5)],
                    'PeakShape': ['U', 'V', 'W']
                },
                limits={
                    'U': [0.0, 0.1],
                    'V': [-0.05, 0.05],
                    'W': [0.0, 0.2]
                },
                cycles=3,
                step=0.1
            )
            results = proj.refine()
            print(f"精修完成\nRwp: {results['Rwp']:.2f}%\nχ²: {results['chi2']:.2f}")
            # 验证精修结果
            if results['Rwp'] > 15.0:
                raise ValueError("精修结果未收敛，请检查输入参数")
            proj.save()
            print("精修完成，结果已保存")
        except Exception as e:
            print(f"错误: {str(e)}")
            sys.exit(1)
        sys.exit(0)
    elif sys.platform == "darwin": 
        application = G2App(0) # create the GUI framework
    else:
        application = wx.App(0) # create the GUI framework
    try:
        GSASIIpath.SetBinaryPath(True)
    except:
        print('Unable to run with current installation, please reset or reinstall')
        # if GSASIIpath.HowIsG2Installed().startswith('git'):
        #     print('use this command w/gitstrap')
        # elif GSASIIpath.HowIsG2Installed().startswith('svn'):
        #     print('use this command w/bootstrap')
        sys.exit()
        # print('Unable to run with current setup, do you want to update to the')
        # try:
        #     if '2' in platform.python_version_tuple()[0]:            
        #         ans = raw_input("latest GSAS-II version? Update ([Yes]/no): ")
        #     else:
        #         ans = input("latest GSAS-II version? Update ([Yes]/no): ")                
        # except:
        #     ans = 'no'
        # if ans.strip().lower() == "no":
        #     import sys
        #     print('Exiting')
        #     sys.exit()
        # print('Updating...')
        # import GSASIIctrlGUI as G2G
        #GSASIIpath.svnUpdateProcess()
        # if GSASIIpath.HowIsG2Installed().startswith('git'):
        #     gitCheckUpdates(None)
        # elif GSASIIpath.HowIsG2Installed().startswith('svn'):
        #     svnCheckUpdates(None)
        # else:
    import GSASIIdataGUI as G2gd
    G2gd.GSASIImain(application) # start the GUI
    if sys.platform == "darwin": 
        wx.CallLater(50,application.ClearStartup)
    GSASIIpath.InvokeDebugOpts()
    application.MainLoop()
