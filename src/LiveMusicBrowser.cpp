#include "imgui/imgui.h"
#include "json11/json11.hpp"
#include "imgui/backends/imgui_impl_glfw.h"
#include "imgui/backends/imgui_impl_opengl3.h"
#include <stdio.h>
#include <stdint.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <fcntl.h>

#include <sys/un.h>
#include <errno.h>
#include <iostream>
#if defined(IMGUI_IMPL_OPENGL_ES2)
#include <GLES2/gl2.h>
#endif
#include <GLFW/glfw3.h> // Will drag system OpenGL headers

const int SOCKET_BUFSIZE = 250*1024;
char buffer[SOCKET_BUFSIZE];

static void glfw_error_callback(int error, const char* description)
{
    fprintf(stderr, "Glfw Error %d: %s\n", error, description);
}

const char* SOCKET_IN = "/tmp/LiveMusicBrowser.ui.socket";

int guard(int n, const char* err) 
{ 
    if (n == -1) 
    { 
        perror(err); 
        exit(1); 
    } 
    return n; 
}

void readInput(int socket, json11::Json& data)
{
    int status = recv(socket, buffer, sizeof(buffer), 0);
    if (status > 0)
    {
        buffer[status] = 0;
        std::string err;
        data = json11::Json::parse(buffer, err);
        if (data.is_null())
        {
            std::cerr << "Parsing data failed: " << err << std::endl;
        }
    }
    else if (errno != EAGAIN)
    {
        perror("recv()");
    }
}

int main(int, char**)
{
    // Setup window
    glfwSetErrorCallback(glfw_error_callback);
    if (!glfwInit())
        return 1;

    int sock;
    struct sockaddr_un name;

    /* Create socket on which to send. */
    sock = guard(socket(AF_UNIX, SOCK_DGRAM, 0), "opening datagram socket");
    {
        int flags = guard(fcntl(sock, F_GETFL), "could not get flags on TCP listening socket");
        guard(fcntl(sock, F_SETFL, flags | O_NONBLOCK), "setting socket to non-blocking");
    }
    {
        int size = SOCKET_BUFSIZE;
        guard(setsockopt(sock, SOL_SOCKET, SO_RCVBUF, &size, sizeof(size)), "set rcvbuf size");
    }
    /* Construct name of socket to send to. */
    name.sun_family = AF_UNIX;
    strcpy(name.sun_path, SOCKET_IN);
    remove(SOCKET_IN);
    guard(bind(sock, (struct sockaddr*) &name, sizeof(struct sockaddr_un)), "binding socket");


    const char* glsl_version = "#version 150";
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 2);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);  // 3.2+ only
    glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GL_TRUE);            // Required on Mac

    // Create window with graphics context
    GLFWwindow* window = glfwCreateWindow(1280, 720, "Sam's Live Music Browser", NULL, NULL);
    if (window == NULL)
        return 1;
    glfwMakeContextCurrent(window);
    glfwSwapInterval(1); // Enable vsync

    // Setup Dear ImGui context
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO(); 
    io.Fonts->AddFontFromFileTTF("/System/Library/Fonts/Supplemental/Arial.ttf", 18);

    // Setup Dear ImGui style
    ImGui::StyleColorsDark();
    //ImGui::StyleColorsClassic();

    // Setup Platform/Renderer backends
    ImGui_ImplGlfw_InitForOpenGL(window, true);
    ImGui_ImplOpenGL3_Init(glsl_version);

    // Our state
    bool show_demo_window = true;
    json11::Json data;
    // Main loop
    while (!glfwWindowShouldClose(window))
    {
        glfwPollEvents();

        // Start the Dear ImGui frame
        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplGlfw_NewFrame();
        ImGui::NewFrame();

        {
            readInput(sock, data);

            ImGuiWindowFlags window_flags = 
                    ImGuiWindowFlags_NoDecoration | 
                    ImGuiWindowFlags_AlwaysAutoResize | 
                    ImGuiWindowFlags_NoSavedSettings | 
                    ImGuiWindowFlags_NoFocusOnAppearing | 
                    ImGuiWindowFlags_NoNav | 
                    ImGuiWindowFlags_NoMouseInputs |
                    ImGuiWindowFlags_NoMove;
            const ImGuiViewport* viewport = ImGui::GetMainViewport();
            ImVec2 work_pos = viewport->WorkPos; // Use work area to avoid menu-bar/task-bar, if any!
            //ImVec2 work_size = viewport->WorkSize;
            ImVec2 window_pos_pivot;
            window_pos_pivot.x = 0.0f;
            window_pos_pivot.y = 0.0f;
            int display_w, display_h;
            glfwGetFramebufferSize(window, &display_w, &display_h);

            ImGui::SetNextWindowPos(work_pos, ImGuiCond_Always, window_pos_pivot);
            ImGui::SetNextWindowBgAlpha(0.f);
            ImGui::SetNextWindowSize(ImVec2(display_w, display_h));
            ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.0f);
            ImGui::Begin("Browse", nullptr, window_flags);                         

            ImGuiTableFlags flags = ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg | ImGuiTableFlags_SizingFixedFit;
            if (not data["rows"].is_null() and ImGui::BeginTable("tracks", data["cols"].array_items().size(), flags))
            {
                for (const auto& col_name: data["cols"].array_items())
                {
                    ImGui::TableSetupColumn(col_name.string_value().c_str());
                }
                ImGui::TableHeadersRow();

                for (int row_ix = 0; row_ix < data["rows"].array_items().size(); row_ix++)
                {
                    const auto& row = data["rows"][row_ix];
                    ImGui::TableNextRow();
                    for (int column = 0; column < row.array_items().size(); column++)
                    {
                        ImGui::TableSetColumnIndex(column);
                        if (column == 0)
                        {
                            ImGui::Selectable(row[column].string_value().c_str(), row_ix == data["sel_ix"].int_value(), ImGuiSelectableFlags_SpanAllColumns);
                        }
                        else
                        {
                            ImGui::TextUnformatted(row[column].string_value().c_str());
                        }
                    }
                }

                ImGui::EndTable();
            }    
            ImGui::End();
            ImGui::PopStyleVar();
        }

        if (show_demo_window)
            ImGui::ShowDemoWindow(&show_demo_window);

        // Rendering
        ImGui::Render();
        int display_w, display_h;
        glfwGetFramebufferSize(window, &display_w, &display_h);
        glViewport(0, 0, display_w, display_h);
        //glClearColor(clear_color.x * clear_color.w, clear_color.y * clear_color.w, clear_color.z * clear_color.w, clear_color.w);
        glClear(GL_COLOR_BUFFER_BIT);
        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());

        glfwSwapBuffers(window);
    }

    // Cleanup
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplGlfw_Shutdown();
    ImGui::DestroyContext();

    glfwDestroyWindow(window);
    glfwTerminate();

    return 0;
}
