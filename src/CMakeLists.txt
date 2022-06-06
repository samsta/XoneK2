cmake_minimum_required(VERSION 3.20)
project(LiveMusicBrowser VERSION 0.1.0)

list(APPEND CMAKE_MODULE_PATH ${CMAKE_SOURCE_DIR}/cmake/Modules)

find_package(OpenGL REQUIRED)
find_package(GLFW REQUIRED)

include_directories(
    .
    imgui
    ${GLFW_INCLUDE_DIR})

add_definitions(
    -std=c++11
    -DGLFW_INCLUDE_GLCOREARB=1
    -DGLFW_INCLUDE_GLEXT=1
    -DGL_SILENCE_DEPRECATION=1
    -Werror
    -Wall
    )

add_executable(LiveMusicBrowser 
    ${CMAKE_SOURCE_DIR}/main.cpp
    ${CMAKE_SOURCE_DIR}/LiveMusicBrowser.cpp
    ${CMAKE_SOURCE_DIR}/imgui/imgui.cpp
    ${CMAKE_SOURCE_DIR}/imgui/imgui_demo.cpp
    ${CMAKE_SOURCE_DIR}/imgui/imgui_draw.cpp
    ${CMAKE_SOURCE_DIR}/imgui/imgui_tables.cpp
    ${CMAKE_SOURCE_DIR}/imgui/imgui_widgets.cpp
    ${CMAKE_SOURCE_DIR}/imgui/backends/imgui_impl_glfw.cpp
    ${CMAKE_SOURCE_DIR}/imgui/backends/imgui_impl_opengl3.cpp
    ${CMAKE_SOURCE_DIR}/json11/json11.cpp
)

target_link_libraries(LiveMusicBrowser ${GLFW_LIBRARY} ${OPENGL_LIBRARY})