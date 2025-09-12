#!/usr/bin/env python
"""
演示PyVista渲染器完整UI功能
"""

import sys
from PyQt5.QtWidgets import QApplication
import qdarkgraystyle

from nucbox.gui.browser.main_window_pyvista import MainWindowPyVista


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkgraystyle.load_stylesheet())
    
    # 创建主窗口
    window = MainWindowPyVista()
    window.setWindowTitle('NucBrowser - PyVista 渲染器（完整UI）')
    
    # 加载数据文件
    import os
    if os.path.exists('test.csv'):
        print("正在加载 test.csv...")
        print("UI组件包括：")
        print("  - 菜单栏：文件、视图、渲染选项")
        print("  - 层管理面板：显示/隐藏、重命名、删除层")
        print("  - 控制面板：调整渲染样式、宽度、颜色等")
        print("  - 3D视图：鼠标交互（旋转、缩放、平移）")
        window.load_particles('test.csv')
    elif os.path.exists('wt.csv'):
        print("正在加载 wt.csv...")
        window.load_particles('wt.csv')
    else:
        print("请提供数据文件（test.csv 或 wt.csv）")
    
    window.show()
    
    print("\n操作说明：")
    print("  文件菜单：打开文件(Ctrl+O)、保存截图(Ctrl+S)")
    print("  视图菜单：显示/隐藏坐标轴、重置相机")
    print("  层面板：管理多个渲染层")
    print("  控制面板：调整渲染参数")
    print("\n鼠标操作：")
    print("  左键拖拽：旋转")
    print("  滚轮：缩放")
    print("  右键拖拽：平移")
    
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())