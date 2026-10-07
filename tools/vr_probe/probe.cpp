#define XR_USE_GRAPHICS_API_VULKAN
#include <openxr/openxr.h>
#include <vulkan/vulkan.h>
#include <openxr/openxr_platform.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
XrInstance g_instance = XR_NULL_HANDLE;

void fail(const char *what, XrResult result) {
    char name[XR_MAX_RESULT_STRING_SIZE] = {};
    if (g_instance != XR_NULL_HANDLE) xrResultToString(g_instance, result, name);
    std::fprintf(stderr, "FAIL %s: %s (%d)\n", what, name[0] ? name : "OpenXR error", int(result));
}

bool xr_ok(XrResult r, const char *what) {
    if (XR_FAILED(r)) { fail(what, r); return false; }
    return true;
}

bool vk_ok(VkResult r, const char *what) {
    if (r != VK_SUCCESS) { std::fprintf(stderr, "FAIL %s: VkResult %d\n", what, int(r)); return false; }
    return true;
}

template <typename T>
bool proc(XrInstance instance, const char *name, T &out) {
    PFN_xrVoidFunction fn = nullptr;
    if (!xr_ok(xrGetInstanceProcAddr(instance, name, &fn), name) || fn == nullptr) return false;
    out = reinterpret_cast<T>(fn);
    return true;
}

struct Eye {
    XrSwapchain swapchain = XR_NULL_HANDLE;
    uint32_t width = 0, height = 0;
    std::vector<XrSwapchainImageVulkan2KHR> images;
    std::vector<VkImageView> views;
    std::vector<VkFramebuffer> framebuffers;
    VkBuffer readbackBuffer = VK_NULL_HANDLE;
    VkDeviceMemory readbackMemory = VK_NULL_HANDLE;
    VkDeviceSize readbackSize = 0;
    bool readbackCoherent = false;
};

struct App {
    XrInstance instance = XR_NULL_HANDLE;
    XrSystemId system = XR_NULL_SYSTEM_ID;
    XrSession session = XR_NULL_HANDLE;
    XrSpace local = XR_NULL_HANDLE;
    VkInstance vkInstance = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    VkRenderPass renderPass = VK_NULL_HANDLE;
    uint32_t queueFamily = 0;
    VkCommandPool commandPool = VK_NULL_HANDLE;
    VkCommandBuffer command = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
    std::array<Eye, 2> eyes;
    PFN_xrGetVulkanGraphicsRequirements2KHR getRequirements = nullptr;
    PFN_xrCreateVulkanInstanceKHR createVulkanInstance = nullptr;
    PFN_xrGetVulkanGraphicsDevice2KHR getGraphicsDevice = nullptr;
    PFN_xrCreateVulkanDeviceKHR createVulkanDevice = nullptr;
    bool sessionRunning = false;
    bool sessionBegun = false;
    uint64_t submittedFrames = 0;
    bool readbackComplete = false;
};

struct ReadbackFiles {
    std::filesystem::path directory;
};

bool init_vulkan(App &a) {
    if (!proc(a.instance, "xrGetVulkanGraphicsRequirements2KHR", a.getRequirements) ||
        !proc(a.instance, "xrCreateVulkanInstanceKHR", a.createVulkanInstance) ||
        !proc(a.instance, "xrGetVulkanGraphicsDevice2KHR", a.getGraphicsDevice) ||
        !proc(a.instance, "xrCreateVulkanDeviceKHR", a.createVulkanDevice)) return false;

    XrGraphicsRequirementsVulkan2KHR req{XR_TYPE_GRAPHICS_REQUIREMENTS_VULKAN2_KHR};
    if (!xr_ok(a.getRequirements(a.instance, a.system, &req), "xrGetVulkanGraphicsRequirements2KHR")) return false;
    std::printf("Vulkan required API %u.%u..%u.%u\n", XR_VERSION_MAJOR(req.minApiVersionSupported), XR_VERSION_MINOR(req.minApiVersionSupported),
                XR_VERSION_MAJOR(req.maxApiVersionSupported), XR_VERSION_MINOR(req.maxApiVersionSupported));

    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "MK64 Steam Frame Eye Probe";
    app.applicationVersion = 1;
    app.pEngineName = "minimal-openxr-probe";
    app.engineVersion = 1;
    const uint32_t minVk = VK_MAKE_API_VERSION(0, XR_VERSION_MAJOR(req.minApiVersionSupported), XR_VERSION_MINOR(req.minApiVersionSupported), 0);
    const uint32_t maxVk = VK_MAKE_API_VERSION(0, XR_VERSION_MAJOR(req.maxApiVersionSupported), XR_VERSION_MINOR(req.maxApiVersionSupported), 0);
    app.apiVersion = std::min<uint32_t>(VK_API_VERSION_1_1, maxVk);
    if (app.apiVersion < minVk) app.apiVersion = minVk;
    VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    ici.pApplicationInfo = &app;
    XrVulkanInstanceCreateInfoKHR xrIci{XR_TYPE_VULKAN_INSTANCE_CREATE_INFO_KHR};
    xrIci.systemId = a.system;
    xrIci.pfnGetInstanceProcAddr = vkGetInstanceProcAddr;
    xrIci.vulkanCreateInfo = &ici;
    VkResult vkResult = VK_ERROR_INITIALIZATION_FAILED;
    if (!xr_ok(a.createVulkanInstance(a.instance, &xrIci, &a.vkInstance, &vkResult), "xrCreateVulkanInstanceKHR") || !vk_ok(vkResult, "runtime Vulkan instance creation")) return false;

    XrVulkanGraphicsDeviceGetInfoKHR getInfo{XR_TYPE_VULKAN_GRAPHICS_DEVICE_GET_INFO_KHR};
    getInfo.systemId = a.system;
    getInfo.vulkanInstance = a.vkInstance;
    if (!xr_ok(a.getGraphicsDevice(a.instance, &getInfo, &a.physical), "xrGetVulkanGraphicsDevice2KHR")) return false;
    VkPhysicalDeviceProperties properties{};
    vkGetPhysicalDeviceProperties(a.physical, &properties);
    std::printf("GPU: %s (Vulkan %u.%u.%u)\n", properties.deviceName, VK_VERSION_MAJOR(properties.apiVersion), VK_VERSION_MINOR(properties.apiVersion), VK_VERSION_PATCH(properties.apiVersion));

    uint32_t familyCount = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(a.physical, &familyCount, nullptr);
    std::vector<VkQueueFamilyProperties> families(familyCount);
    vkGetPhysicalDeviceQueueFamilyProperties(a.physical, &familyCount, families.data());
    bool found = false;
    for (uint32_t i = 0; i < familyCount; ++i) if ((families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) && families[i].queueCount) { a.queueFamily = i; found = true; break; }
    if (!found) { std::fprintf(stderr, "FAIL no graphics queue family\n"); return false; }
    float priority = 1.0f;
    VkDeviceQueueCreateInfo qci{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    qci.queueFamilyIndex = a.queueFamily;
    qci.queueCount = 1;
    qci.pQueuePriorities = &priority;
    VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    dci.queueCreateInfoCount = 1;
    dci.pQueueCreateInfos = &qci;
    XrVulkanDeviceCreateInfoKHR xrDci{XR_TYPE_VULKAN_DEVICE_CREATE_INFO_KHR};
    xrDci.systemId = a.system;
    xrDci.pfnGetInstanceProcAddr = vkGetInstanceProcAddr;
    xrDci.vulkanPhysicalDevice = a.physical;
    xrDci.vulkanCreateInfo = &dci;
    vkResult = VK_ERROR_INITIALIZATION_FAILED;
    if (!xr_ok(a.createVulkanDevice(a.instance, &xrDci, &a.device, &vkResult), "xrCreateVulkanDeviceKHR") || !vk_ok(vkResult, "runtime Vulkan device creation")) return false;
    vkGetDeviceQueue(a.device, a.queueFamily, 0, &a.queue);

    VkCommandPoolCreateInfo pci{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    pci.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    pci.queueFamilyIndex = a.queueFamily;
    if (!vk_ok(vkCreateCommandPool(a.device, &pci, nullptr, &a.commandPool), "vkCreateCommandPool")) return false;
    VkCommandBufferAllocateInfo cai{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    cai.commandPool = a.commandPool;
    cai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    cai.commandBufferCount = 1;
    if (!vk_ok(vkAllocateCommandBuffers(a.device, &cai, &a.command), "vkAllocateCommandBuffers")) return false;
    VkFenceCreateInfo fci{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    if (!vk_ok(vkCreateFence(a.device, &fci, nullptr, &a.fence), "vkCreateFence")) return false;
    VkAttachmentDescription attachment{};
    attachment.format = VK_FORMAT_R8G8B8A8_UNORM;
    attachment.samples = VK_SAMPLE_COUNT_1_BIT;
    attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
    attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
    attachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
    attachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
    attachment.initialLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
    attachment.finalLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
    VkAttachmentReference colorRef{0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VkSubpassDescription subpass{};
    subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
    subpass.colorAttachmentCount = 1;
    subpass.pColorAttachments = &colorRef;
    VkSubpassDependency dependency{};
    dependency.srcSubpass = VK_SUBPASS_EXTERNAL;
    dependency.dstSubpass = 0;
    dependency.srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
    dependency.dstStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
    dependency.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
    VkRenderPassCreateInfo rpci{VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO};
    rpci.attachmentCount = 1;
    rpci.pAttachments = &attachment;
    rpci.subpassCount = 1;
    rpci.pSubpasses = &subpass;
    rpci.dependencyCount = 1;
    rpci.pDependencies = &dependency;
    if (!vk_ok(vkCreateRenderPass(a.device, &rpci, nullptr, &a.renderPass), "vkCreateRenderPass UNORM")) return false;
    return true;
}

bool create_eye(App &a, Eye &eye, uint32_t width, uint32_t height, bool needReadback) {
    eye.width = width; eye.height = height;
    XrSwapchainCreateInfo sci{XR_TYPE_SWAPCHAIN_CREATE_INFO};
    sci.usageFlags = XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT | XR_SWAPCHAIN_USAGE_MUTABLE_FORMAT_BIT |
        (needReadback ? XR_SWAPCHAIN_USAGE_TRANSFER_SRC_BIT : 0);
    sci.format = VK_FORMAT_R8G8B8A8_SRGB;
    sci.sampleCount = 1; sci.width = width; sci.height = height;
    sci.faceCount = sci.arraySize = sci.mipCount = 1;
    if (!xr_ok(xrCreateSwapchain(a.session, &sci, &eye.swapchain), "xrCreateSwapchain eye")) return false;
    uint32_t count = 0;
    if (!xr_ok(xrEnumerateSwapchainImages(eye.swapchain, 0, &count, nullptr), "xrEnumerateSwapchainImages count")) return false;
    eye.images.assign(count, XrSwapchainImageVulkan2KHR{XR_TYPE_SWAPCHAIN_IMAGE_VULKAN2_KHR});
    if (!xr_ok(xrEnumerateSwapchainImages(eye.swapchain, count, &count, reinterpret_cast<XrSwapchainImageBaseHeader *>(eye.images.data())), "xrEnumerateSwapchainImages")) return false;
    for (const auto &image : eye.images) {
        VkImageViewCreateInfo vci{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
        vci.image = image.image;
        vci.viewType = VK_IMAGE_VIEW_TYPE_2D;
        vci.format = VK_FORMAT_R8G8B8A8_UNORM;
        vci.components = {VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_IDENTITY};
        vci.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        VkImageView view = VK_NULL_HANDLE;
        if (!vk_ok(vkCreateImageView(a.device, &vci, nullptr, &view), "vkCreateImageView UNORM")) return false;
        eye.views.push_back(view);
        VkFramebufferCreateInfo fbci{VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};
        fbci.renderPass = a.renderPass;
        fbci.attachmentCount = 1;
        fbci.pAttachments = &view;
        fbci.width = width;
        fbci.height = height;
        fbci.layers = 1;
        VkFramebuffer framebuffer = VK_NULL_HANDLE;
        if (!vk_ok(vkCreateFramebuffer(a.device, &fbci, nullptr, &framebuffer), "vkCreateFramebuffer UNORM")) return false;
        eye.framebuffers.push_back(framebuffer);
    }
    if (needReadback) {
        eye.readbackSize = VkDeviceSize(width) * height * 4;
        VkBufferCreateInfo bci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
        bci.size = eye.readbackSize;
        bci.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
        bci.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        if (!vk_ok(vkCreateBuffer(a.device, &bci, nullptr, &eye.readbackBuffer), "vkCreateBuffer readback")) return false;
        VkMemoryRequirements requirements{};
        vkGetBufferMemoryRequirements(a.device, eye.readbackBuffer, &requirements);
        VkPhysicalDeviceMemoryProperties memoryProperties{};
        vkGetPhysicalDeviceMemoryProperties(a.physical, &memoryProperties);
        uint32_t memoryType = UINT32_MAX;
        int bestScore = -1;
        for (uint32_t i = 0; i < memoryProperties.memoryTypeCount; ++i) {
            if ((requirements.memoryTypeBits & (1u << i)) == 0) continue;
            const VkMemoryPropertyFlags flags = memoryProperties.memoryTypes[i].propertyFlags;
            if ((flags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT) == 0) continue;
            const int score = ((flags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) ? 2 : 0) + ((flags & VK_MEMORY_PROPERTY_HOST_CACHED_BIT) ? 1 : 0);
            if (score > bestScore) { memoryType = i; bestScore = score; }
        }
        if (memoryType == UINT32_MAX) { std::fprintf(stderr, "FAIL no host-visible memory type for readback\n"); return false; }
        const VkMemoryPropertyFlags memoryFlags = memoryProperties.memoryTypes[memoryType].propertyFlags;
        eye.readbackCoherent = (memoryFlags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) != 0;
        VkMemoryAllocateInfo mai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        mai.allocationSize = requirements.size;
        mai.memoryTypeIndex = memoryType;
        if (!vk_ok(vkAllocateMemory(a.device, &mai, nullptr, &eye.readbackMemory), "vkAllocateMemory readback") ||
            !vk_ok(vkBindBufferMemory(a.device, eye.readbackBuffer, eye.readbackMemory, 0), "vkBindBufferMemory readback")) return false;
    }
    return true;
}

bool render_eye(App &a, Eye &eye, const std::array<float, 4> &color, bool capture, std::vector<uint8_t> &pixels) {
    XrSwapchainImageAcquireInfo ai{XR_TYPE_SWAPCHAIN_IMAGE_ACQUIRE_INFO};
    uint32_t index = 0;
    if (!xr_ok(xrAcquireSwapchainImage(eye.swapchain, &ai, &index), "xrAcquireSwapchainImage")) return false;
    XrSwapchainImageWaitInfo wi{XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO}; wi.timeout = XR_INFINITE_DURATION;
    if (!xr_ok(xrWaitSwapchainImage(eye.swapchain, &wi), "xrWaitSwapchainImage")) return false;
    auto failAfterWait = [&]() {
        (void)vkDeviceWaitIdle(a.device);
        XrSwapchainImageReleaseInfo release{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO};
        (void)xrReleaseSwapchainImage(eye.swapchain, &release);
        return false;
    };

    if (!vk_ok(vkResetCommandBuffer(a.command, 0), "vkResetCommandBuffer")) return failAfterWait();
    VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    if (!vk_ok(vkBeginCommandBuffer(a.command, &bi), "vkBeginCommandBuffer")) return failAfterWait();
    VkClearValue clear{};
    std::copy(color.begin(), color.end(), clear.color.float32);
    VkRenderPassBeginInfo rbi{VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};
    rbi.renderPass = a.renderPass;
    rbi.framebuffer = eye.framebuffers[index];
    rbi.renderArea.extent = {eye.width, eye.height};
    rbi.clearValueCount = 1;
    rbi.pClearValues = &clear;
    vkCmdBeginRenderPass(a.command, &rbi, VK_SUBPASS_CONTENTS_INLINE);
    vkCmdEndRenderPass(a.command);
    if (capture) {
        VkImageMemoryBarrier toTransfer{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
        toTransfer.srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
        toTransfer.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
        toTransfer.oldLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
        toTransfer.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        toTransfer.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toTransfer.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toTransfer.image = eye.images[index].image;
        toTransfer.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        vkCmdPipelineBarrier(a.command, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0, nullptr, 1, &toTransfer);
        VkBufferImageCopy copy{};
        copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        copy.imageExtent = {eye.width, eye.height, 1};
        vkCmdCopyImageToBuffer(a.command, eye.images[index].image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, eye.readbackBuffer, 1, &copy);
        VkBufferMemoryBarrier toHost{VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER};
        toHost.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        toHost.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
        toHost.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toHost.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toHost.buffer = eye.readbackBuffer;
        toHost.offset = 0;
        toHost.size = eye.readbackSize;
        vkCmdPipelineBarrier(a.command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0, 0, nullptr, 1, &toHost, 0, nullptr);
        VkImageMemoryBarrier toRuntime{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
        toRuntime.srcAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
        toRuntime.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_READ_BIT | VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
        toRuntime.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        toRuntime.newLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
        toRuntime.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toRuntime.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toRuntime.image = eye.images[index].image;
        toRuntime.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        vkCmdPipelineBarrier(a.command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, 0, 0, nullptr, 0, nullptr, 1, &toRuntime);
    }
    if (!vk_ok(vkEndCommandBuffer(a.command), "vkEndCommandBuffer")) return failAfterWait();
    if (!vk_ok(vkResetFences(a.device, 1, &a.fence), "vkResetFences")) return failAfterWait();
    VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO}; submit.commandBufferCount = 1; submit.pCommandBuffers = &a.command;
    if (!vk_ok(vkQueueSubmit(a.queue, 1, &submit, a.fence), "vkQueueSubmit") || !vk_ok(vkWaitForFences(a.device, 1, &a.fence, VK_TRUE, UINT64_MAX), "vkWaitForFences")) return failAfterWait();
    if (capture) {
        void *mapped = nullptr;
        if (!vk_ok(vkMapMemory(a.device, eye.readbackMemory, 0, VK_WHOLE_SIZE, 0, &mapped), "vkMapMemory readback")) return failAfterWait();
        if (!eye.readbackCoherent) {
            VkMappedMemoryRange range{VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE};
            range.memory = eye.readbackMemory;
            range.offset = 0;
            range.size = VK_WHOLE_SIZE;
            if (!vk_ok(vkInvalidateMappedMemoryRanges(a.device, 1, &range), "vkInvalidateMappedMemoryRanges")) {
                vkUnmapMemory(a.device, eye.readbackMemory);
                return failAfterWait();
            }
        }
        pixels.resize(size_t(eye.readbackSize));
        std::memcpy(pixels.data(), mapped, pixels.size());
        vkUnmapMemory(a.device, eye.readbackMemory);
    }
    XrSwapchainImageReleaseInfo ri{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO};
    return xr_ok(xrReleaseSwapchainImage(eye.swapchain, &ri), "xrReleaseSwapchainImage");
}

void destroy(App &a) {
    if (a.device) vkDeviceWaitIdle(a.device);
    for (Eye &e : a.eyes) {
        for (VkFramebuffer framebuffer : e.framebuffers) vkDestroyFramebuffer(a.device, framebuffer, nullptr);
        for (VkImageView view : e.views) vkDestroyImageView(a.device, view, nullptr);
        if (e.readbackBuffer) vkDestroyBuffer(a.device, e.readbackBuffer, nullptr);
        if (e.readbackMemory) vkFreeMemory(a.device, e.readbackMemory, nullptr);
        if (e.swapchain) xrDestroySwapchain(e.swapchain);
    }
    if (a.local) xrDestroySpace(a.local);
    if (a.session) xrDestroySession(a.session);
    if (a.device) {
        if (a.renderPass) vkDestroyRenderPass(a.device, a.renderPass, nullptr);
        if (a.fence) vkDestroyFence(a.device, a.fence, nullptr);
        if (a.commandPool) vkDestroyCommandPool(a.device, a.commandPool, nullptr);
        vkDestroyDevice(a.device, nullptr);
    }
    if (a.vkInstance) vkDestroyInstance(a.vkInstance, nullptr);
    if (a.instance) xrDestroyInstance(a.instance);
}

bool save_and_verify_readback(const std::filesystem::path &directory, const char *eyeName, const Eye &eye,
                              const std::vector<uint8_t> &rgba, const std::array<uint8_t, 4> &expected) {
    if (rgba.size() != size_t(eye.width) * eye.height * 4) {
        std::fprintf(stderr, "FAIL %s readback byte count: got %zu, expected %llu\n", eyeName, rgba.size(),
            static_cast<unsigned long long>(VkDeviceSize(eye.width) * eye.height * 4));
        return false;
    }
    const auto rawPath = directory / (std::string(eyeName) + ".rgba");
    const auto ppmPath = directory / (std::string(eyeName) + ".ppm");
    {
        std::ofstream raw(rawPath, std::ios::binary);
        if (!raw || !raw.write(reinterpret_cast<const char *>(rgba.data()), std::streamsize(rgba.size()))) {
            std::fprintf(stderr, "FAIL writing %s\n", rawPath.c_str()); return false;
        }
    }
    {
        std::ofstream ppm(ppmPath, std::ios::binary);
        if (!ppm) { std::fprintf(stderr, "FAIL opening %s\n", ppmPath.c_str()); return false; }
        ppm << "P6\n" << eye.width << " " << eye.height << "\n255\n";
        for (size_t i = 0; i < rgba.size(); i += 4) ppm.write(reinterpret_cast<const char *>(rgba.data() + i), 3);
        if (!ppm) { std::fprintf(stderr, "FAIL writing %s\n", ppmPath.c_str()); return false; }
    }
    bool matches = true;
    for (size_t i = 0; i < rgba.size(); i += 4) {
        for (size_t channel = 0; channel < 4; ++channel) {
            if (std::abs(int(rgba[i + channel]) - int(expected[channel])) > 1) matches = false;
        }
    }
    const size_t center = (size_t(eye.height / 2) * eye.width + eye.width / 2) * 4;
    std::printf("Readback %s %ux%u center RGBA=%u,%u,%u,%u expected=%u,%u,%u,%u uniform=%s files=%s,%s\n",
        eyeName, eye.width, eye.height, rgba[center], rgba[center + 1], rgba[center + 2], rgba[center + 3],
        expected[0], expected[1], expected[2], expected[3], matches ? "yes" : "no", rawPath.c_str(), ppmPath.c_str());
    if (!matches) std::fprintf(stderr, "FAIL %s readback did not match the expected clear across every pixel\n", eyeName);
    return matches;
}

bool run(double seconds, const ReadbackFiles *readbackFiles) {
    App a;
    uint32_t extCount = 0;
    if (!xr_ok(xrEnumerateInstanceExtensionProperties(nullptr, 0, &extCount, nullptr), "enumerate runtime extensions")) return false;
    std::vector<XrExtensionProperties> exts(extCount, XrExtensionProperties{XR_TYPE_EXTENSION_PROPERTIES});
    if (!xr_ok(xrEnumerateInstanceExtensionProperties(nullptr, extCount, &extCount, exts.data()), "enumerate runtime extensions")) return false;
    bool haveEnable2 = false;
    for (auto &e : exts) if (!std::strcmp(e.extensionName, XR_KHR_VULKAN_ENABLE2_EXTENSION_NAME)) haveEnable2 = true;
    if (!haveEnable2) { std::fprintf(stderr, "FAIL runtime does not advertise %s\n", XR_KHR_VULKAN_ENABLE2_EXTENSION_NAME); return false; }
    const char *enabled[] = {XR_KHR_VULKAN_ENABLE2_EXTENSION_NAME};
    XrInstanceCreateInfo ici{XR_TYPE_INSTANCE_CREATE_INFO};
    std::strncpy(ici.applicationInfo.applicationName, "MK64 Frame Eye Probe", XR_MAX_APPLICATION_NAME_SIZE - 1);
    ici.applicationInfo.applicationVersion = 1;
    std::strncpy(ici.applicationInfo.engineName, "minimal-openxr-probe", XR_MAX_ENGINE_NAME_SIZE - 1);
    ici.applicationInfo.engineVersion = 1;
    ici.applicationInfo.apiVersion = XR_API_VERSION_1_0;
    ici.enabledExtensionCount = 1; ici.enabledExtensionNames = enabled;
    if (!xr_ok(xrCreateInstance(&ici, &a.instance), "xrCreateInstance")) return false;
    g_instance = a.instance;
    XrInstanceProperties ip{XR_TYPE_INSTANCE_PROPERTIES};
    XrSystemGetInfo sgi{XR_TYPE_SYSTEM_GET_INFO}; sgi.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
    XrSystemProperties sp{XR_TYPE_SYSTEM_PROPERTIES};
    if (!xr_ok(xrGetInstanceProperties(a.instance, &ip), "xrGetInstanceProperties") || !xr_ok(xrGetSystem(a.instance, &sgi, &a.system), "xrGetSystem HMD") ||
        !xr_ok(xrGetSystemProperties(a.instance, a.system, &sp), "xrGetSystemProperties")) { destroy(a); return false; }
    std::printf("Runtime: %s %u.%u.%u; system: %s\n", ip.runtimeName, XR_VERSION_MAJOR(ip.runtimeVersion), XR_VERSION_MINOR(ip.runtimeVersion), XR_VERSION_PATCH(ip.runtimeVersion), sp.systemName);
    if (!init_vulkan(a)) { destroy(a); return false; }

    XrGraphicsBindingVulkan2KHR binding{XR_TYPE_GRAPHICS_BINDING_VULKAN2_KHR};
    binding.instance = a.vkInstance; binding.physicalDevice = a.physical; binding.device = a.device;
    binding.queueFamilyIndex = a.queueFamily; binding.queueIndex = 0;
    XrSessionCreateInfo sci{XR_TYPE_SESSION_CREATE_INFO}; sci.next = &binding; sci.systemId = a.system;
    if (!xr_ok(xrCreateSession(a.instance, &sci, &a.session), "xrCreateSession")) { destroy(a); return false; }
    XrReferenceSpaceCreateInfo spaceInfo{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
    spaceInfo.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_LOCAL; spaceInfo.poseInReferenceSpace.orientation.w = 1.0f;
    if (!xr_ok(xrCreateReferenceSpace(a.session, &spaceInfo, &a.local), "xrCreateReferenceSpace LOCAL")) { destroy(a); return false; }

    uint32_t viewCount = 0;
    if (!xr_ok(xrEnumerateViewConfigurationViews(a.instance, a.system, XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO, 0, &viewCount, nullptr), "enumerate stereo views") || viewCount != 2) {
        std::fprintf(stderr, "FAIL PRIMARY_STEREO returned %u views (expected 2)\n", viewCount); destroy(a); return false;
    }
    std::array<XrViewConfigurationView, 2> viewConfigs{XrViewConfigurationView{XR_TYPE_VIEW_CONFIGURATION_VIEW}, XrViewConfigurationView{XR_TYPE_VIEW_CONFIGURATION_VIEW}};
    if (!xr_ok(xrEnumerateViewConfigurationViews(a.instance, a.system, XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO, 2, &viewCount, viewConfigs.data()), "read stereo view sizes")) { destroy(a); return false; }
    uint32_t formatCount = 0;
    if (!xr_ok(xrEnumerateSwapchainFormats(a.session, 0, &formatCount, nullptr), "enumerate swapchain formats")) { destroy(a); return false; }
    std::vector<int64_t> formats(formatCount);
    if (!xr_ok(xrEnumerateSwapchainFormats(a.session, formatCount, &formatCount, formats.data()), "read swapchain formats")) { destroy(a); return false; }
    if (std::find(formats.begin(), formats.end(), int64_t(VK_FORMAT_R8G8B8A8_SRGB)) == formats.end()) {
        std::fprintf(stderr, "FAIL runtime does not expose VK_FORMAT_R8G8B8A8_SRGB\n"); destroy(a); return false;
    }
    std::printf("Eye sizes: L %ux%u, R %ux%u; format: R8G8B8A8_SRGB images with R8G8B8A8_UNORM views\n",
        viewConfigs[0].recommendedImageRectWidth, viewConfigs[0].recommendedImageRectHeight,
        viewConfigs[1].recommendedImageRectWidth, viewConfigs[1].recommendedImageRectHeight);

    const auto start = Clock::now();
    bool failed = false;
    while (std::chrono::duration<double>(Clock::now() - start).count() < seconds && !failed && !a.readbackComplete) {
        XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
        while (xrPollEvent(a.instance, &event) == XR_SUCCESS) {
            if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                auto *changed = reinterpret_cast<XrEventDataSessionStateChanged *>(&event);
                const char *name = "UNKNOWN";
                switch (changed->state) {
                    case XR_SESSION_STATE_IDLE: name="IDLE"; break; case XR_SESSION_STATE_READY: name="READY"; break;
                    case XR_SESSION_STATE_SYNCHRONIZED: name="SYNCHRONIZED"; break; case XR_SESSION_STATE_VISIBLE: name="VISIBLE"; break;
                    case XR_SESSION_STATE_FOCUSED: name="FOCUSED"; break; case XR_SESSION_STATE_STOPPING: name="STOPPING"; break;
                    case XR_SESSION_STATE_EXITING: name="EXITING"; break; case XR_SESSION_STATE_LOSS_PENDING: name="LOSS_PENDING"; break;
                    default: break;
                }
                std::printf("Session state: %s\n", name);
                if (changed->state == XR_SESSION_STATE_READY) {
                    XrSessionBeginInfo begin{XR_TYPE_SESSION_BEGIN_INFO}; begin.primaryViewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
                    failed = !xr_ok(xrBeginSession(a.session, &begin), "xrBeginSession");
                    a.sessionBegun = !failed; a.sessionRunning = a.sessionBegun;
                    if (a.sessionRunning) for (int i = 0; i < 2 && !failed; ++i) failed = !create_eye(a, a.eyes[i], viewConfigs[i].recommendedImageRectWidth, viewConfigs[i].recommendedImageRectHeight, readbackFiles != nullptr);
                } else if (changed->state == XR_SESSION_STATE_STOPPING && a.sessionBegun) {
                    failed = !xr_ok(xrEndSession(a.session), "xrEndSession"); a.sessionBegun = false; a.sessionRunning = false;
                } else if (changed->state == XR_SESSION_STATE_EXITING || changed->state == XR_SESSION_STATE_LOSS_PENDING) {
                    a.sessionRunning = false; a.sessionBegun = false;
                }
            }
            event = {XR_TYPE_EVENT_DATA_BUFFER};
        }
        if (!a.sessionRunning) { std::this_thread::sleep_for(std::chrono::milliseconds(5)); continue; }
        XrFrameWaitInfo fwi{XR_TYPE_FRAME_WAIT_INFO}; XrFrameState fs{XR_TYPE_FRAME_STATE};
        if (!xr_ok(xrWaitFrame(a.session, &fwi, &fs), "xrWaitFrame")) { failed = true; break; }
        XrFrameBeginInfo fbi{XR_TYPE_FRAME_BEGIN_INFO};
        if (!xr_ok(xrBeginFrame(a.session, &fbi), "xrBeginFrame")) { failed = true; break; }
        std::array<XrCompositionLayerProjectionView, 2> projectionViews{
            XrCompositionLayerProjectionView{XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW},
            XrCompositionLayerProjectionView{XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW}};
        bool render = fs.shouldRender;
        const bool capture = render && readbackFiles != nullptr && !a.readbackComplete;
        std::array<std::vector<uint8_t>, 2> capturedPixels;
        if (render) {
            XrViewLocateInfo locate{XR_TYPE_VIEW_LOCATE_INFO}; locate.viewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
            locate.displayTime = fs.predictedDisplayTime; locate.space = a.local;
            XrViewState viewState{XR_TYPE_VIEW_STATE}; std::array<XrView, 2> views{XrView{XR_TYPE_VIEW}, XrView{XR_TYPE_VIEW}};
            uint32_t located = 0;
            if (!xr_ok(xrLocateViews(a.session, &locate, &viewState, 2, &located, views.data()), "xrLocateViews") || located != 2) { failed = true; }
            if (!failed && (viewState.viewStateFlags & (XR_VIEW_STATE_POSITION_VALID_BIT | XR_VIEW_STATE_ORIENTATION_VALID_BIT)) !=
                    (XR_VIEW_STATE_POSITION_VALID_BIT | XR_VIEW_STATE_ORIENTATION_VALID_BIT)) {
                std::fprintf(stderr, "FAIL xrLocateViews returned invalid eye poses\n"); failed = true;
            }
            for (uint32_t i = 0; i < 2 && !failed; ++i) {
                const std::array<float, 4> colors = {i == 0 ? 0.90f : 0.05f, i == 0 ? 0.05f : 0.15f, i == 0 ? 0.10f : 0.90f, 1.0f};
                if (!render_eye(a, a.eyes[i], colors, capture, capturedPixels[i])) { failed = true; break; }
                projectionViews[i].pose = views[i].pose;
                projectionViews[i].fov = views[i].fov;
                projectionViews[i].subImage.swapchain = a.eyes[i].swapchain;
                projectionViews[i].subImage.imageRect.offset = {0, 0};
                projectionViews[i].subImage.imageRect.extent = {int32_t(a.eyes[i].width), int32_t(a.eyes[i].height)};
                projectionViews[i].subImage.imageArrayIndex = 0;
            }
        }
        XrCompositionLayerProjection projection{XR_TYPE_COMPOSITION_LAYER_PROJECTION};
        projection.space = a.local; projection.viewCount = 2; projection.views = projectionViews.data();
        const XrCompositionLayerBaseHeader *layers[] = {reinterpret_cast<const XrCompositionLayerBaseHeader *>(&projection)};
        XrFrameEndInfo end{XR_TYPE_FRAME_END_INFO}; end.displayTime = fs.predictedDisplayTime;
        end.environmentBlendMode = XR_ENVIRONMENT_BLEND_MODE_OPAQUE;
        if (render && !failed) { end.layerCount = 1; end.layers = layers; }
        XrResult endResult = xrEndFrame(a.session, &end);
        if (!xr_ok(endResult, "xrEndFrame")) failed = true;
        else if (render && !failed) {
            ++a.submittedFrames;
            if (capture) {
                const bool leftOk = save_and_verify_readback(readbackFiles->directory, "left", a.eyes[0], capturedPixels[0], {230, 13, 26, 255});
                const bool rightOk = save_and_verify_readback(readbackFiles->directory, "right", a.eyes[1], capturedPixels[1], {13, 38, 230, 255});
                if (leftOk && rightOk) {
                    a.readbackComplete = true;
                    std::puts("Readback validation: PASS (distinct left/right eye colors)");
                } else failed = true;
            }
        }
    }

    // Leave a running session through the runtime's STOPPING -> xrEndSession sequence.
    if (a.sessionBegun) {
        if (!xr_ok(xrRequestExitSession(a.session), "xrRequestExitSession")) failed = true;
        const auto stopDeadline = Clock::now() + std::chrono::seconds(2);
        while (a.sessionBegun && Clock::now() < stopDeadline) {
            XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
            while (xrPollEvent(a.instance, &event) == XR_SUCCESS) {
                if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                    auto *changed = reinterpret_cast<XrEventDataSessionStateChanged *>(&event);
                    if (changed->state == XR_SESSION_STATE_STOPPING) {
                        if (!xr_ok(xrEndSession(a.session), "xrEndSession")) failed = true;
                        a.sessionBegun = false;
                        a.sessionRunning = false;
                    } else if (changed->state == XR_SESSION_STATE_EXITING || changed->state == XR_SESSION_STATE_LOSS_PENDING) {
                        a.sessionBegun = false;
                        a.sessionRunning = false;
                    }
                }
                event = {XR_TYPE_EVENT_DATA_BUFFER};
            }
            if (a.sessionBegun) std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        if (a.sessionBegun) {
            std::fprintf(stderr, "FAIL runtime did not stop the session within 2 seconds\n");
            failed = true;
        }
    }
    std::printf("Submitted valid stereo frames: %llu\n", static_cast<unsigned long long>(a.submittedFrames));
    if (readbackFiles && !a.readbackComplete) {
        std::fprintf(stderr, "FAIL readback mode ended without a captured and validated submitted frame\n");
        failed = true;
    }
    destroy(a);
    return !failed && a.submittedFrames > 0;
}
}

int main(int argc, char **argv) {
    double seconds = 30.0;
    ReadbackFiles readback;
    bool readbackRequested = false;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--seconds") == 0 && i + 1 < argc) {
            char *end = nullptr; seconds = std::strtod(argv[++i], &end);
            if (!end || *end || !std::isfinite(seconds) || seconds < 0.1 || seconds > 3600) {
                std::fprintf(stderr, "usage: %s [--seconds 0.1..3600] [--readback-dir PATH]\n", argv[0]); return 2;
            }
        } else if (std::strcmp(argv[i], "--readback-dir") == 0 && i + 1 < argc) {
            readback.directory = argv[++i];
            readbackRequested = true;
        } else {
            std::fprintf(stderr, "usage: %s [--seconds 0.1..3600] [--readback-dir PATH]\n", argv[0]); return 2;
        }
    }
    if (readbackRequested) {
        std::error_code ec;
        std::filesystem::create_directories(readback.directory, ec);
            if (ec || !std::filesystem::is_directory(readback.directory, ec)) {
            std::fprintf(stderr, "FAIL creating readback directory %s: %s\n", readback.directory.c_str(), ec.message().c_str());
            return 2;
        }
    }
    if (!run(seconds, readbackRequested ? &readback : nullptr)) { std::fprintf(stderr, "PROBE FAILED: no valid rendered stereo frames\n"); return 1; }
    std::puts("PROBE PASSED"); return 0;
}
