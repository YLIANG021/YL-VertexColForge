# YL VertexColForge

**一个面向 Blender 5.x 的全能顶点色/颜色属性工作站。**

![主宣传图/界面概览](请在此处替换_你的主宣传图或概览动图.gif)

YL VertexColForge 彻底改变了 Blender 中的颜色属性（Color Attribute）编辑体验。它不仅仅是一个顶点绘制工具，而是专为游戏资产制作、风格化渲染和技术美术打造的“通道级”遮罩与颜色处理中心。无论是打包 RGBA Mask、烘焙曲率与光照，还是传递数据，都在一个直观的面板中一站式完成。

---

## 🌐 多语言支持
原生支持 13 种界面语言：简体中文、繁体中文、英语、日语、韩语、德语、法语、西班牙语、意大利语、波兰语、葡萄牙语、俄语和越南语。

---

## ✨ 核心特性

### 1. 👁️ 所见即所得通道预览
突破默认视图限制，直接查看 RGB、Alpha 或任意单独通道。

<img width="442" height="320" alt="切换图层和预览单通道" src="https://github.com/user-attachments/assets/e9b759f4-fa53-4045-a5b5-a5a5c9a4d2fe" />


### 2. 🎨 笔刷、填充和吸管工具
画笔工具只影响所选区域。快速绘画和拾取颜色，互不干扰。

<img width="492" height="320" alt="笔刷(1)" src="https://github.com/user-attachments/assets/06543287-d0a9-49b8-8d3b-1274cc7ad0cd" />


### 3. 🌈 任意方向视口渐变
任意方向，任意颜色,实时预览，使用 ColorRamp 在 3D 视图中直接拖拽绘制线性或圆形渐变。

<img width="470" height="320" alt="屏幕渐变(1)" src="https://github.com/user-attachments/assets/b23acbc5-fcbc-4b2d-9a6f-ce447b320898" />



### 4. 🗺️ 实时 UV 渐变
直接在 UV中沿 UV 岛方向创建渐变遮罩，完美契合贴图空间的工作流。

<img width="490" height="320" alt="uv渐变" src="https://github.com/user-attachments/assets/aaa9fd96-ca94-4c22-80cb-5e493c3554c2" />


### 5. ⚡ 快速颜色选择
在视口中点击可见颜色，拖动鼠标即可调整容差并实时查看选择范围，高效隔离需要编辑的区域。

<img width="448" height="320" alt="选择" src="https://github.com/user-attachments/assets/a9c7d93c-e951-4acf-9708-4713128a1b64" />


### 6. 🪞 一键颜色镜像
在视口中点一下即可完成镜像，系统会自动判断，不必再繁琐地手动选择轴向或正负方向。支持通道复制。

<img width="492" height="320" alt="镜像" src="https://github.com/user-attachments/assets/6520a184-189b-408e-b2ef-4cef72531f97" />

### 7. 💡 AO、方向光和曲率遮罩
一键烘焙几何与光照信息，生成到可编辑的颜色属性中，为风格化贴图奠定明暗基础。

<img width="492" height="320" alt="Light AO" src="https://github.com/user-attachments/assets/b2de0de0-7181-40b1-8f3f-2607ab9fbec7" />


### 8. 🧪 实时颜色调整
非破坏性预览色阶（Levels）、伽马、HSV、反转、平滑模糊和 Ramp 重映射，确认效果完美后再点击应用。
<img width="492" height="320" alt="ADJUST" src="https://github.com/user-attachments/assets/eded699e-6700-470a-afa0-6f4bc8987cdd" />


### 9. 🎲 结构化随机颜色
支持按连接网格、UV 岛、材质、锐边、角度、顶点组、面或顶点生成随机颜色，制作 ID Map 的最快途径。

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
