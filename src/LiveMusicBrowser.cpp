#include "imgui/imgui.h"
#include "json11/json11.hpp"

static bool filter_bpm = false;

void drawFilters(const json11::Json& data, json11::Json& send_data)
{
    filter_bpm = data["bpm_filter"].bool_value();
    ImGui::Checkbox("Filter BPM", &filter_bpm);
    if (filter_bpm != data["bpm_filter"].bool_value())
    {
        send_data = json11::Json::object{{"bpm_filter", json11::Json(filter_bpm)}};
    }
}

void drawPlayingTracks(const json11::Json& data)
{
    ImGui::Text("Now Playing:");
    ImGuiTableFlags flags = ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg | ImGuiTableFlags_SizingFixedFit;

    if (not data["playing"].is_null() and ImGui::BeginTable("playing", data["cols"].array_items().size() + 1, flags))
    {
        ImGui::TableSetupColumn("Deck");
        for (const auto& col_name: data["cols"].array_items())
        {
            ImGui::TableSetupColumn(col_name.string_value().c_str());
        }
        ImGui::TableHeadersRow();

        for (const auto& track: data["playing"].object_items())
        {
            ImGui::TableNextRow();
            ImGui::TableSetColumnIndex(0);
            ImGui::TextUnformatted(track.first.c_str());
            for (int column = 1; column <= track.second.array_items().size(); column++)
            {
                ImGui::TableSetColumnIndex(column);
                ImGui::TextUnformatted(track.second[column-1].string_value().c_str());
            }
        }
        ImGui::EndTable();
    }    
}

void drawBrowserList(const json11::Json& data)
{
    ImGui::Text("Browse Files:");
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
}


void drawFrame(int display_w, int display_h, const json11::Json& data, json11::Json& send_data)
{
    ImGuiWindowFlags window_flags = 
            ImGuiWindowFlags_NoDecoration | 
            ImGuiWindowFlags_AlwaysAutoResize | 
            ImGuiWindowFlags_NoSavedSettings | 
            ImGuiWindowFlags_NoFocusOnAppearing | 
            ImGuiWindowFlags_NoNav | 
            ImGuiWindowFlags_NoMove;
    const ImGuiViewport* viewport = ImGui::GetMainViewport();
    ImVec2 work_pos = viewport->WorkPos; // Use work area to avoid menu-bar/task-bar, if any!
    //ImVec2 work_size = viewport->WorkSize;
    ImVec2 window_pos_pivot;
    window_pos_pivot.x = 0.0f;
    window_pos_pivot.y = 0.0f;

    ImGui::SetNextWindowPos(work_pos, ImGuiCond_Always, window_pos_pivot);
    ImGui::SetNextWindowBgAlpha(0.f);
    ImGui::SetNextWindowSize(ImVec2(display_w, display_h));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.0f);
    ImGui::Begin("Browse", nullptr, window_flags);                         

    drawPlayingTracks(data);
    ImGui::Separator();
    drawFilters(data, send_data);
    ImGui::Separator();
    drawBrowserList(data);

    ImGui::End();
    ImGui::PopStyleVar();
}
