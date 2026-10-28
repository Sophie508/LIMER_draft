# This backend builds exactly one application owned by LIMER.
add_executable(scratch_LimerSimulator LimerSimulator.cc)
target_include_directories(scratch_LimerSimulator PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(scratch_LimerSimulator "${ns3-libs}" "${ns3-contrib-libs}" "${ns3-external-libs}")
set_runtime_outputdirectory(LimerSimulator ${CMAKE_OUTPUT_DIRECTORY}/scratch/ scratch_)
