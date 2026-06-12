# YL VertexColForge

**一个面向 Blender 5.x 的全能顶点色/颜色属性工作站。**


YL VertexColForge 彻底改变了 Blender 中的颜色属性（Color Attribute）编辑体验。它不仅仅是一个顶点绘制工具，而是专为游戏资产制作、风格化渲染和技术美术打造的“通道级”遮罩与颜色处理中心。无论是打包 RGBA Mask、烘焙曲率与光照，还是传递数据，都在一个直观的面板中一站式完成。

---

## 🌐 多语言支持
原生支持 13 种界面语言：简体中文、繁体中文、英语、日语、韩语、德语、法语、西班牙语、意大利语、波兰语、葡萄牙语、俄语和越南语。

---

## ✨ 核心特性

### 1. 👁️ 所见即所得通道预览
突破默认视图限制，直接查看 RGB、Alpha 或任意单独通道。

<img width="426" height="320" alt="切换图层和预览单通道" src="https://github.com/user-attachments/assets/7311c0c2-a2d8-4903-8508-61fccca22827" />


### 2. 🎨 笔刷、填充和吸管工具
画笔工具只影响所选区域。快速绘画和拾取颜色，互不干扰。

<img width="426" height="320" alt="笔刷" src="https://github.com/user-attachments/assets/a379dab9-33fe-49b2-b8c8-e1e32c323ee2" />



### 3. 🌈 任意方向视口渐变
任意方向，任意颜色,实时预览，使用 ColorRamp 在 3D 视图中直接拖拽绘制线性或圆形渐变。

<img width="426" height="320" alt="屏幕渐变" src="https://github.com/user-attachments/assets/6918da9a-8944-4a77-a5f1-61594bf87fc9" />

### 4. 🗺️ 实时 UV 渐变
直接在 UV中沿 UV 岛方向创建渐变遮罩，完美契合贴图空间的工作流。

<img width="426" height="320" alt="uv渐变" src="https://github.com/user-attachments/assets/e4d2307c-9a4a-4d2e-96b1-abdfec75ffda" />



### 5. ⚡ 快速颜色选择
在视口中点击可见颜色，拖动鼠标即可调整容差并实时查看选择范围，高效隔离需要编辑的区域。

<img width="426" height="320" alt="选择(1)" src="https://github.com/user-attachments/assets/b3172d9b-6d97-4e91-bab9-637afd6013df" />




### 6. 🪞 一键颜色镜像
在视口中点一下即可完成镜像，系统会自动判断，不必再繁琐地手动选择轴向或正负方向。支持通道复制。

<img width="426" height="320" alt="镜像" src="https://github.com/user-attachments/assets/05fb3548-4673-4cbf-84d7-8cea1080d6f8" />



### 7. 💡 AO、方向光和曲率遮罩
一键烘焙几何与光照信息，生成到可编辑的颜色属性中，为风格化贴图奠定明暗基础。

<img width="426" height="320" alt="Light AO" src="https://github.com/user-attachments/assets/5c140cbd-ff24-4856-a489-c9d62106ef16" />


### 8. 🧪 实时颜色调整
非破坏性预览色阶（Levels）、伽马、HSV、反转、平滑模糊和 Ramp 重映射，确认效果完美后再点击应用。
<img width="426" height="320" alt="ADJUST" src="https://github.com/user-attachments/assets/a6c2c6e3-1997-48da-850b-50b0c3d620e6" />



### 9. 🎲 结构化随机颜色
支持按连接网格、UV 岛、材质、锐边、角度、顶点组、面或顶点生成随机颜色，制作 ID Map 的最快途径。
<img width="426" height="320" alt="随机" src="https://github.com/user-attachments/assets/b017049a-6a03-4af9-b898-88f3c73cab7d" />


### 10. 🔁 贴图、权重和物体传递
轻松在图像（Texture）、顶点组（Vertex Group）和具有不同拓扑的网格对象（Mesh）之间双向移动颜色数据。

---

## 📦 安装指南

1. 确保使用的是 **Blender 5.0** 或更高版本。
2. 下载扩展包 `.zip`，或克隆此仓库。
3. 在 Blender 中打开 `编辑 (Edit) > 偏好设置 (Preferences) > 扩展 (Extensions)`。
4. 从磁盘安装该插件并启用 `YL VertexColForge`。
5. 在 3D 视图中选中一个网格，按 `N` 打开侧边栏，即可在 `YL VertexColForge` 面板开始创作。

## 📄 许可证

* 插件 Python 代码采用 `GPL-3.0-or-later` 许可证。
* `assets/` 目录中的捆绑资源采用 `CC0-1.0` 许可证。
