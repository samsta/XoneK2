#include "imgui/imgui.h"
#include "json11/json11.hpp"

static bool filter_bpm = false;
static bool filter_key = false;
static float bpm_percentage = 5;

void drawFilters(const json11::Json& data, json11::Json& send_data)
{
    filter_key = data["key_filter"].bool_value();
    ImGui::Checkbox("Filter Key", &filter_key);
    if (filter_key != data["key_filter"].bool_value())
    {
        send_data = json11::Json::object{{"key_filter", json11::Json(filter_key)}};
    }

    ImGui::SameLine();

    filter_bpm = data["bpm_filter"].bool_value();
    ImGui::Checkbox("Filter BPM", &filter_bpm);
    if (filter_bpm != data["bpm_filter"].bool_value())
    {
        send_data = json11::Json::object{{"bpm_filter", json11::Json(filter_bpm)}};
    }

    ImGui::SameLine();

    bpm_percentage = data["bpm_percent"].number_value();
    float percentage_step = 1.0;
    ImGui::InputScalar("BPM range", ImGuiDataType_Float,  &bpm_percentage, &percentage_step, &percentage_step, "%3.1f%%");
    if (bpm_percentage != float(data["bpm_percent"].number_value()))
    {
        send_data = json11::Json::object{{"bpm_percent", json11::Json(bpm_percentage)}};
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
                if (track.second[column-1].is_number()) {
                    ImGui::Text("%3.5g", track.second[column-1].number_value());
                } else {
                    ImGui::TextUnformatted(track.second[column-1].string_value().c_str());
                }
            }
        }
        ImGui::EndTable();
    }    
}

void drawBrowserList(const json11::Json& data)
{
    ImGui::Text("Browse Files:");
    ImGuiTableFlags flags = ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg | ImGuiTableFlags_SizingFixedFit;

    int key_distance_col_ix = -1;
    if (not data["rows"].is_null() and ImGui::BeginTable("tracks", data["cols"].array_items().size(), flags))
    {
        int col_ix = 0;
        for (const auto& col_name: data["cols"].array_items())
        {
            ImGui::TableSetupColumn(col_name.string_value().c_str());
            if (col_name.string_value() == "KeyDistance")
            {
                key_distance_col_ix = col_ix;
            }
            col_ix++;
        }
        ImGui::TableHeadersRow();

        bool needs_color_pop = false;
        for (int row_ix = 0; row_ix < data["rows"].array_items().size(); row_ix++)
        {
            const auto& row = data["rows"][row_ix];

            float key_distance = -1;
            ImGui::TableNextRow();
            // Note: the color of this row will be used on the next call to TableNextRow
            if (needs_color_pop)
            {
                ImGui::PopStyleColor(2);
                needs_color_pop = false;
            }
            if (key_distance_col_ix >= 0 and not row[key_distance_col_ix].is_null())
            {
                key_distance = row[key_distance_col_ix].number_value();
                if (key_distance >= 0)
                {
                    const float green_hue = 0.23;
                    float hue = green_hue - key_distance / 20;
                    if (hue < 0) hue = 0;
                    ImVec4 row_color = (ImVec4)ImColor::HSV(hue, 1.0f, 0.6f);
                    ImGui::PushStyleColor(ImGuiCol_TableRowBg,    row_color);
                    ImGui::PushStyleColor(ImGuiCol_TableRowBgAlt, row_color);
                    needs_color_pop = true;
                }
            }


            for (int column = 0; column < row.array_items().size(); column++)
            {
                ImGui::TableSetColumnIndex(column);
                if (column == 0)
                {
                    ImGui::Selectable(row[column].string_value().c_str(), row_ix == data["sel_ix"].int_value(), ImGuiSelectableFlags_SpanAllColumns);
                }
                else
                {
                    if (row[column].is_number()) {
                        ImGui::Text("%3.5g", row[column].number_value());
                    } else {
                        ImGui::TextUnformatted(row[column].string_value().c_str());
                    }
                }
            }
        }

        ImGui::EndTable();
        if (needs_color_pop)
        {
            ImGui::PopStyleColor(2);
        }
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
