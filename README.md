### Logeswaran Sivakumar

ML systems, GPU performance and agentic AI.

AI Optimization Engineer at Solidigm (SK Hynix) in Portland, OR. I work on making training and
inference faster: GPU kernels, compilers and runtimes, and the hardware underneath. M.S. in Computer
Science from Oregon State University, where I worked on fused CUDA kernels for point cloud networks.
Previously at AMD, Samsung and MulticoreWare.

[Website](https://logeswaranofficial.com) · [LinkedIn](https://www.linkedin.com/in/logeswaransivakumar) · [Medium](https://logessiva.medium.com)

#### Projects

- [tessiq](https://github.com/Logeswaran123/tessiq): out-of-tree PyTorch backend for NVIDIA GPUs, with a device runtime, a `torch.compile` compiler with its own IR and passes, and a kernel library.
- [Fused PointConv](https://github.com/Logeswaran123/ml-pointconvformer-optim): fused CUDA and CUTLASS forward pass for PointConv, and an inverse KNN index map that turns the backward atomic scatter into a gather. 1.9× forward, 1.6× backward on an H100 at 400k points.
- [Distilling LLMs with RAG](https://github.com/Logeswaran123/distilling-step-by-step-rag): Llama 3 distilled into T5 with retrieval-augmented step-by-step reasoning, 67× smaller.
- [Multiscale Template Matching](https://github.com/Logeswaran123/Multiscale-Template-Matching): locates a cropped region in its source image across unknown scales with SIFT and FLANN.
- [Stable Diffusion Playground](https://github.com/Logeswaran123/Stable-Diffusion-Playground): image and 2D/3D video generation with latent diffusion models.
- [Mr. Pose](https://github.com/Logeswaran123/MrPose): real-time pose estimation that scores exercise form and counts reps.

#### Writing

- [Building an Out-of-Tree PyTorch Backend, End to End](https://logeswaranofficial.com/blog/building-a-pytorch-backend/) · Oct 2026
- [Understanding and Exploring 3D Gaussian Splatting](https://logeswaranofficial.com/blog/3d-gaussian-splatting/) · Dec 2023
- [Mr. Pose: An Easy Guide for Pose Estimation with Google's MediaPipe](https://logeswaranofficial.com/blog/pose-estimation-with-mediapipe/) · Oct 2022
- [Playground for Stable Diffusion](https://logeswaranofficial.com/blog/stable-diffusion-playground/) · Oct 2022
