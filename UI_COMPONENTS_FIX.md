# PyVista UI组件修复说明

## 问题描述
原始PyVista实现缺少了VisPy版本中的UI组件，包括：
- 层管理面板
- 控制面板
- 菜单栏功能
- 文件操作界面

## 修复内容

### 1. 恢复完整菜单栏
- 使用原有的 `MenuBar` 类
- 支持文件打开、保存截图
- 坐标轴显示/隐藏
- 相机重置功能

### 2. 集成层管理面板
- 创建 `CanvasControlPyVista` 类继承原有控制面板
- 支持层的显示/隐藏、重命名、删除
- 保留原有的层列表UI设计
- 染色体标签自动更新

### 3. 控制面板集成
- 渲染样式选择（line/tube/points/ribbon/surface）
- 线宽/管径调整
- 颜色模式切换（彩虹渐变/单色）
- 透明度控制

### 4. 主窗口布局恢复
- 左侧：3D视图（PyVista渲染器）
- 右侧：控制面板（包含层管理和属性控制）
- 可调整分割比例
- 保持原有850:250的默认布局

## 文件修改

### 新增文件
- `canvas_control_pyvista.py` - PyVista兼容的控制面板
- `obj_panel_pyvista.py` - PyVista层的属性面板
- `demo_pyvista_ui.py` - UI功能演示脚本

### 修改文件
- `main_window_pyvista.py` - 集成完整UI组件
- `canvas_pyvista.py` - 使用PyVista控制面板
- `layers_pyvista.py` - 兼容控制面板接口

## 使用方法

### 基本使用
```bash
# 使用PyVista渲染器（包含完整UI）
python -m nucbox.gui.browser data.csv --renderer pyvista

# 运行演示脚本
python demo_pyvista_ui.py
```

### UI操作
1. **文件操作**
   - Ctrl+O: 打开CSV文件
   - Ctrl+S: 保存截图

2. **层管理**
   - 点击眼睛图标：显示/隐藏层
   - 点击重命名图标：修改层名称
   - 点击删除图标：删除层

3. **渲染控制**
   - Style下拉菜单：切换渲染样式
   - Width滑块：调整线宽/管径
   - Color下拉菜单：选择颜色模式

## 性能优势
- GPU加速渲染
- 更流畅的交互响应
- 支持大规模数据集
- 更好的视觉质量

## 兼容性
- 完全兼容原有VisPy界面操作
- 保留所有原有UI组件功能
- 支持在两种渲染器间切换